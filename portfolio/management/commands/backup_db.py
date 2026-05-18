import gzip
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Dump PostgreSQL database, gzip it, and upload to a GCS bucket.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--bucket',
            default=os.environ.get('BACKUP_GCS_BUCKET', ''),
            help='GCS bucket name (or set BACKUP_GCS_BUCKET env var).',
        )
        parser.add_argument(
            '--keep-local',
            action='store_true',
            help='Keep the local .sql.gz file after upload.',
        )

    def handle(self, *args, **options):
        bucket = options['bucket']
        if not bucket:
            self.stderr.write(self.style.ERROR(
                'No bucket specified. Use --bucket or set BACKUP_GCS_BUCKET.'))
            return

        db = settings.DATABASES['default']
        if db['ENGINE'] not in ('django.db.backends.postgresql', 'django.db.backends.postgresql_psycopg2'):
            self.stderr.write(self.style.ERROR(
                f"Unsupported DB engine: {db['ENGINE']}. Only PostgreSQL is supported."))
            return

        stamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
        sql_name = f"vault_{stamp}.sql"
        gz_name = f"{sql_name}.gz"

        tmpdir = tempfile.mkdtemp(prefix='vault_backup_')
        sql_path = os.path.join(tmpdir, sql_name)
        gz_path = os.path.join(tmpdir, gz_name)

        try:
            self._dump(db, sql_path)
            self._compress(sql_path, gz_path)
            self._upload(gz_path, bucket, gz_name)

            self.stdout.write(self.style.SUCCESS(
                f"Backup uploaded → gs://{bucket}/{gz_name}"))
        except Exception as e:
            logger.exception("Backup failed")
            self.stderr.write(self.style.ERROR(f"Backup failed: {e}"))
        finally:
            if not options['keep_local']:
                shutil.rmtree(tmpdir, ignore_errors=True)

    def _dump(self, db, dest):
        """Run pg_dump and write the SQL to dest."""
        env = os.environ.copy()
        if db.get('PASSWORD'):
            env['PGPASSWORD'] = db['PASSWORD']

        cmd = [
            'pg_dump',
            '--no-owner',
            '--no-privileges',
            '-h', db.get('HOST', 'localhost'),
            '-p', str(db.get('PORT', 5432)),
            '-U', db.get('USER', 'postgres'),
            '-d', db['NAME'],
            '-f', dest,
        ]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {result.stderr.strip()}")
        self.stdout.write(f"  pg_dump → {dest}")

    def _compress(self, src, dest):
        """Gzip the SQL dump."""
        with open(src, 'rb') as f_in, gzip.open(dest, 'wb') as f_out:
            while chunk := f_in.read(1 << 20):
                f_out.write(chunk)
        size_mb = os.path.getsize(dest) / (1 << 20)
        self.stdout.write(f"  gzip    → {dest} ({size_mb:.1f} MB)")

    def _upload(self, local_path, bucket_name, object_name):
        """Upload file to GCS using the project's service account."""
        from google.cloud import storage

        from pftracker.utils import get_google_credentials_path
        client = storage.Client.from_service_account_json(get_google_credentials_path())
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.upload_from_filename(local_path)
        self.stdout.write(f"  upload  → gs://{bucket_name}/{object_name}")
