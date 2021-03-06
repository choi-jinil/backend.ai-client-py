from . import register_command
from .pretty import print_wait, print_done, print_fail
from ..exceptions import BackendError
from ..kernel import Kernel


@register_command
def logs(args):
    '''
    Shows the output logs of a running container.
    '''
    try:
        print_wait('Retrieving container logs...')
        kernel = Kernel(args.sess_id_or_alias)
        result = kernel.get_logs().get('result')
        logs = result.get('logs') if 'logs' in result else ''
        print(logs)
        print_done('End of logs.')
    except BackendError as e:
        print_fail(str(e))
        return


logs.add_argument('sess_id_or_alias', metavar='NAME',
                  help='The session ID or its alias '
                       'given when creating the session.')
