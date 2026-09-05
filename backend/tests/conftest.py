import pytest
import os
import database

# Force in-memory DB for unit test suite so tests run completely isolated, fast, and without requiring a local mongo daemon
database._use_memory_db = True
