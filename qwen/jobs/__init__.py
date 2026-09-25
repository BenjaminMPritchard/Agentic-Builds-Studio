import importlib
import pkgutil


def load_all():
    """{job name: module} for every module in this package that defines a job."""
    jobs = {}
    for m in pkgutil.iter_modules(__path__):
        if m.name.startswith("_"):
            continue
        mod = importlib.import_module(f"{__name__}.{m.name}")
        jobs[mod.NAME] = mod
    return jobs
