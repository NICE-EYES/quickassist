"""Запуск без консольного окна (pythonw run.pyw). Используется и для автозапуска."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from quickassist.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
