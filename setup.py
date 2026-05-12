from setuptools import find_packages, setup


setup(
    name="aws-diagram",
    version="0.1.0",
    description="AWS architecture diagram generator",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.9",
)
