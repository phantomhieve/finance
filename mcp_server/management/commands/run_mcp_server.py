"""
Django management command to start the Vault MCP server.

Usage:
    python manage.py run_mcp_server            # stdio (default — for Gemini CLI)
    python manage.py run_mcp_server --sse      # SSE  (for remote clients)
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Start the Vault MCP (Model Context Protocol) server'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sse',
            action='store_true',
            default=False,
            help='Run in SSE (HTTP) mode instead of stdio',
        )
        parser.add_argument(
            '--port',
            type=int,
            default=8808,
            help='Port for SSE mode (default: 8808)',
        )

    def handle(self, *args, **options):
        from mcp_server.server import mcp

        transport = 'sse' if options['sse'] else 'stdio'

        self.stdout.write(self.style.SUCCESS(
            f'Starting Vault MCP server ({transport} transport)...'
        ))
        self.stdout.write(
            'Resources: 18  |  Tools: 22  |  Audit logging: enabled'
        )

        if transport == 'sse':
            mcp.run(transport='sse', port=options['port'])
        else:
            mcp.run(transport='stdio')
