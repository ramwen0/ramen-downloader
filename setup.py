from setuptools import setup, find_packages

setup(
    name="ramen-downloader",
    version="1.0.0",
    description="A simple YouTube playlist downloader",
    author="ramen",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "customtkinter>=5.2.0",
        "yt-dlp>=2023.11.16",
        "pillow>=10.0.0",  # Required by customtkinter
    ],
    entry_points={
        "console_scripts": [
            "ramen-downloader=ramen_downloader.main:main",
        ],
    },
    python_requires=">=3.8",
    include_package_data=True,
)