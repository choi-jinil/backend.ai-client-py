import getpass
from pathlib import Path
import sys
import traceback

from humanize import naturalsize
from tabulate import tabulate

from . import register_command
from ..compat import token_hex
from ..exceptions import BackendError
from .pretty import print_info, print_wait, print_done, print_fail
from ..kernel import Kernel


def exec_loop(kernel, code, mode, opts=None,
              vprint_wait=print_wait, vprint_done=print_done):
    opts = opts if opts else {}
    run_id = None  # use server-assigned run ID
    while True:
        result = kernel.execute(run_id, code, mode=mode, opts=opts)
        run_id = result['runId']
        opts.clear()  # used only once
        for rec in result['console']:
            if rec[0] == 'stdout':
                print(rec[1], end='', file=sys.stdout)
            elif rec[0] == 'stderr':
                print(rec[1], end='', file=sys.stderr)
            else:
                print('----- output record (type: {0}) -----'.format(rec[0]))
                print(rec[1])
                print('----- end of record -----')
        sys.stdout.flush()
        if result['status'] == 'build-finished':
            exitCode = result.get('exitCode')
            vprint_done('Build finished. (exit code = {0})'.format(exitCode))
            mode = 'continue'
            code = ''
        elif result['status'] == 'finished':
            exitCode = result.get('exitCode')
            vprint_done('Finished. (exit code = {0})'.format(exitCode))
            break
        elif result['status'] == 'waiting-input':
            mode = 'input'
            if result['options'].get('is_password', False):
                code = getpass.getpass()
            else:
                code = input()
        elif result['status'] == 'continued':
            mode = 'continue'
            code = ''


def _noop(*args, **kwargs):
    pass


def _format_stats(stats):
    formatted = []
    for k, v in stats.items():
        if k.endswith('_size') or k.endswith('_bytes'):
            v = naturalsize(v, binary=True)
        elif k == 'cpu_used':
            k += '_msec'
            v = '{0:,}'.format(int(v))
        else:
            v = '{0:,}'.format(int(v))
        formatted.append((k, v))
    return tabulate(formatted)


@register_command
def run(args):
    '''
    Run the given code snippet or files in a session.
    Depending on the session ID you give (default is random),
    it may reuse an existing session or create a new one.
    '''
    if args.quiet:
        vprint_info = vprint_wait = vprint_done = _noop
    else:
        vprint_info = print_info
        vprint_wait = print_wait
        vprint_done = print_done
    if not args.client_token:
        args.client_token = token_hex(16)
        vprint_wait('Creating a temporary kernel...')
    else:
        vprint_info('Client session token: {0}'.format(args.client_token))
        vprint_wait('Connecting to the kernel...')
    if args.env is not None:
        envs = {k: v for k, v in map(lambda s: s.split('=', 1), args.env)}
    else:
        envs = {}
    try:
        kernel = Kernel.get_or_create(
            args.lang, args.client_token,
            mounts=args.mount,
            envs=envs)
    except BackendError as e:
        print_fail(str(e))
        return
    if kernel.created:
        vprint_done('Session {0} is ready.'.format(kernel.kernel_id))
    else:
        vprint_done('Reusing session {0}...'.format(kernel.kernel_id))

    try:
        if args.files:
            if args.code:
                print('You can run only either source files or command-line '
                      'code snippet.', file=sys.stderr)
                return
            vprint_wait('Uploading source files...')
            args.files = [
                str(Path(path).resolve()
                    .relative_to(Path('.').resolve()))
                for path in args.files
            ]
            ret = kernel.upload(args.files)
            if ret.status // 100 != 2:
                print_fail('Uploading source files failed!')
                print('{0}: {1}\n{2}'.format(
                    ret.status, ret.reason, ret.text()))
                return
            vprint_done('Uploading done.')
            build_cmd = args.build if args.build else '*'
            exec_cmd = args.exec if args.exec else '*'
            exec_loop(kernel, '', 'batch', opts={
                'build': build_cmd,
                'exec': exec_cmd,
            }, vprint_wait=vprint_wait, vprint_done=vprint_done)
        else:
            if not args.code:
                print('You should provide the command-line code snippet using '
                      '"-c" option if run without files.', file=sys.stderr)
                return
            exec_loop(kernel, args.code, 'query',
                      vprint_wait=vprint_wait, vprint_done=vprint_done)
    except BackendError as e:
        print_fail(str(e))
    except Exception:
        print_fail('Execution failed!')
        traceback.print_exc()
    finally:
        if args.rm:
            vprint_wait('Cleaning up the session...')
            ret = kernel.destroy()
            vprint_done('Cleaned up the session.')
            if args.stats:
                stats = ret.get('stats', None) if ret else None
                if stats:
                    print(_format_stats(stats))
                else:
                    print('Statistics is not available.')


run.add_argument('lang',
                 help='The runtime or programming language name')
run.add_argument('files', nargs='*',
                 help='The code file(s). Can be added multiple times')
run.add_argument('-t', '--client-token', metavar='SESSID',
                 help='Specify a human-readable session ID or name '
                      '[default: a random hex-string]')
run.add_argument('-c', '--code', metavar='CODE',
                 help='The code snippet as a single string')
run.add_argument('--build', metavar='CMD',
                 help='Custom shell command for building the given files')
run.add_argument('--exec', metavar='CMD',
                 help='Custom shell command for executing the given files')
run.add_argument('--rm', action='store_true', default=False,
                 help='Terminate the session immediately after running '
                      'the given code or files [default: False]')
run.add_argument('-e', '--env', metavar='KEY=VAL', type=str, action='append',
                 help='Environment variable '
                      '(may appear multiple times)')
run.add_argument('-m', '--mount', type=str, action='append',
                 help='User-owned virtual folder names to mount')
run.add_argument('-s', '--stats', action='store_true', default=False,
                 help='Show resource usage statistics after termination '
                      '(only works if "--rm" is given)')
run.add_argument('-q', '--quiet', action='store_true', default=False,
                 help='Hide execution details but show only the kernel'
                      'outputs')


@register_command
def terminate(args):
    '''
    Terminate the given session.
    '''
    print_wait('Terminating the session...')
    try:
        kernel = Kernel(args.sess_id_or_alias)
        ret = kernel.destroy()
    except BackendError as e:
        print_fail(str(e))
        return
    else:
        print_done('Done.')
        if args.stats:
            stats = ret.get('stats', None) if ret else None
            if stats:
                print(_format_stats(stats))
            else:
                print('Statistics is not available.')


terminate.add_argument('sess_id_or_alias', metavar='NAME',
                       help='The session ID or its alias '
                            'given when creating the session.')
terminate.add_argument('-s', '--stats', action='store_true', default=False,
                       help='Show resource usage statistics after termination')
