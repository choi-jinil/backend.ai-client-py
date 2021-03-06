from typing import Iterable, Mapping, Optional, Sequence
import uuid

import aiohttp.web

from .base import BaseFunction, SyncFunctionMixin
from .exceptions import BackendClientError
from .request import Request

__all__ = (
    'BaseKernel',
    'Kernel',
)


class BaseKernel(BaseFunction):

    '''
    Implements the request creation and response handling logic,
    while delegating the process of request sending to the subclasses
    via the generator protocol.
    '''

    @classmethod
    def _get_or_create(cls, lang: str,
                       client_token: Optional[str]=None,
                       mounts: Optional[Iterable[str]]=None,
                       envs: Optional[Mapping[str, str]]=None,
                       max_mem: int=0, exec_timeout: int=0) -> str:
        if client_token:
            assert 4 <= len(client_token) <= 64, \
                   'Client session token should be 4 to 64 characters long.'
        else:
            client_token = uuid.uuid4().hex
        resp = yield Request('POST', '/kernel/create', {
            'lang': lang,
            'clientSessionToken': client_token,
            'config': {
                'mounts': mounts,
                'envs': envs,
            },
            # 'limits': {
            #     'maxMem': max_mem,
            #     'execTimeout': exec_timeout,
            # },
        })
        data = resp.json()
        o = cls(data['kernelId'])  # type: ignore
        o.created = data.get('created', True)  # True is for legacy
        return o

    def _destroy(self):
        resp = yield Request('DELETE', '/kernel/{}'.format(self.kernel_id))
        if resp.status == 200:
            return resp.json()

    def _restart(self):
        yield Request('PATCH', '/kernel/{}'.format(self.kernel_id))

    def _interrupt(self):
        yield Request('POST', '/kernel/{}/interrupt'.format(self.kernel_id))

    def _complete(self, code: str, opts: Optional[dict]=None):
        opts = {} if opts is None else opts
        rqst = Request('POST', '/kernel/{}/complete'.format(self.kernel_id), {
            'code': code,
            'options': {
                'row': int(opts.get('row', 0)),
                'col': int(opts.get('col', 0)),
                'line': opts.get('line', ''),
                'post': opts.get('post', ''),
            },
        })
        resp = yield rqst
        return resp.json()

    def _get_info(self):
        resp = yield Request('GET', '/kernel/{}'.format(self.kernel_id))
        return resp.json()

    def _get_logs(self):
        resp = yield Request('GET', '/kernel/{}/logs'.format(self.kernel_id))
        return resp.json()

    def _execute(self, run_id: Optional[str]=None,
                 code: Optional[str]=None,
                 mode: str='query',
                 opts: Optional[dict]=None):
        opts = {} if opts is None else opts
        if mode in {'query', 'continue', 'input'}:
            assert code is not None  # but maybe empty due to continuation
            rqst = Request('POST', '/kernel/{}'.format(self.kernel_id), {
                'mode': mode,
                'code': code,
                'runId': run_id,
            })
        elif mode == 'batch':
            rqst = Request('POST', '/kernel/{}'.format(self.kernel_id), {
                'mode': mode,
                'code': code,
                'runId': run_id,
                'options': {
                    'build': opts.get('build', None),
                    'buildLog': bool(opts.get('buildLog', False)),
                    'exec': opts.get('exec', None),
                },
            })
        elif mode == 'complete':
            rqst = Request('POST', '/kernel/{}/complete'.format(self.kernel_id), {
                'code': code,
                'options': {
                    'row': int(opts.get('row', 0)),
                    'col': int(opts.get('col', 0)),
                    'line': opts.get('line', ''),
                    'post': opts.get('post', ''),
                },
            })
        else:
            raise BackendClientError('Invalid execution mode: {0}'.format(mode))
        resp = yield rqst
        return resp.json()['result']

    def __init__(self, kernel_id: str) -> None:
        self.kernel_id = kernel_id
        self.destroy  = self._call_base_method(self._destroy)
        self.restart  = self._call_base_method(self._restart)
        self.interrupt = self._call_base_method(self._interrupt)
        self.complete  = self._call_base_method(self._complete)
        self.get_info = self._call_base_method(self._get_info)
        self.get_logs = self._call_base_method(self._get_logs)
        self.execute  = self._call_base_method(self._execute)

    def __init_subclass__(cls):
        cls.get_or_create = cls._call_base_clsmethod(cls._get_or_create)


class Kernel(SyncFunctionMixin, BaseKernel):

    def upload(self, files: Sequence[str]):
        rqst = Request('POST', '/kernel/{}/upload'.format(self.kernel_id))
        rqst.content = [
            # name filename file content_type headers
            aiohttp.web.FileField(
                'src', path, open(path, 'rb'), 'application/octet-stream', None
            ) for path in files
        ]
        return rqst.send()
