from setuptools import setup, find_packages

setup(
    name='ucair3d',
    version='0.1',
    packages=find_packages(),
    description='Reusable PyQt5 components and UI files for 3D visualization',
    author='Your Name',
    include_package_data=True,
    extras_require={
        'graphing': ['pyqtgraph>=0.13.0'],
    },
)
