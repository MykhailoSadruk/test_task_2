import atexit
import os
import tempfile

_database_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
atexit.register(_database_dir.cleanup)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_database_dir.name}/test.db"
