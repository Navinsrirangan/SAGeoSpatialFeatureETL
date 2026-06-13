from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("sa-geospatial-feature-etl")
except PackageNotFoundError:
    __version__ = "0.0.0"
