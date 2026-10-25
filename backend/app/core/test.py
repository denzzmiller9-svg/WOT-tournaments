from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
print(f'__file__: {__file__}')
print(f'Path(__file__).resolve(): {Path(__file__).resolve()}')
print(f'Path(__file__).resolve().parents[3]: {Path(__file__).resolve().parents[3]}')
print(ENV_FILE)