import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="buildstream_license_checker",
    version="0.0.1",
    author="Douglas Winship",
    author_email="douglas.winship@codethink.co.uk",
    description="A tool for extracting license information for BuildStream projects",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://gitlab.com/DouglasWinship/buildstream-licence-checker",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "bst_license_checker = buildstream_license_checker.bst_license_checker:main"
        ]
    },
)
