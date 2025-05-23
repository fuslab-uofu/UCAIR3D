from setuptools import setup, find_packages

setup(
    name='ucair3d',
    version='0.1.0',
    packages=find_packages(),
    include_package_data=True,          # ← honors your MANIFEST.in
    # if you need to be explicit about resource files:
    package_data={
        "ucair3d.ui": ["*.ui", "*.qss", "*.png", "*.svg"],
    },
    description='Reusable PyQt5 components and UI files for 3D visualization',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Michelle Kline',
    author_email='michelle.kline@utah.edu',
    python_requires=">=3.9"
)
