from tabulate import tabulate

from ...agent import Agent
from . import admin


@admin.register_command
def agents(args):
    '''
    List and manage agents.
    '''
    fields = [
        ('ID', 'id'),
        ('Status', 'status'),
        ('First Contact', 'first_contact'),
        ('Mem.Slots', 'mem_slots'),
        ('CPU Slots', 'cpu_slots'),
        ('GPU Slots', 'gpu_slots'),
    ]
    items = Agent.list(args.status,
                       fields=(item[1] for item in fields))
    if len(items) == 0:
        print('There are no matching agents.')
        return
    print(tabulate((item.values() for item in items),
                   headers=(item[0] for item in fields)))


agents.add_argument('-s', '--status', type=str, default='ALIVE',
                    help='Filter agents by the given status.')
