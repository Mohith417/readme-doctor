from setuptools import setup, find_packages

setup(
    name="readme-doctor",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "requests",
        "click",
        "python-dotenv",
    ],
    entry_points={
        "console_scripts": [
            "readme-doctor=readme_doctor.cli:main",
        ],
    },
    author="Mohith417",
    description="AI-powered README health checker for GitHub repositories",
    long_description=open("README.md").read(),
    url="https://github.com/Mohith417/readme-doctor",
    python_requires=">=3.10",
)