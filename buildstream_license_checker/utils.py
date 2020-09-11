#
#  Copyright 2020 Codethink Limited
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#  Authors:
#        Douglas Winship <douglas.winship@codethink.co.uk>

"""
Utilities
=========
Contains utility functions for the BuildStream License Checker tool
"""

import shutil
import sys


def abort():
    """Print short message and exit"""

    print("Aborting buildstream-license-checker", file=sys.stderr)
    sys.exit(1)


def confirm_scanning_software_installed():
    """Confirms that the license scanning software is installed, so it can be run using
    subprocess.run"""
    if not shutil.which("licensecheck"):
        # shutil.which will return None, if licensecheck isn't installed
        print(
            "Error, licensecheck does not seem to be installed."
            " (licensecheck is a perl script which scans source code and detects"
            " license information. bst_license_checker needs licensecheck to run)",
            file=sys.stderr,
        )
        abort()


def confirm_buildstream_installed():
    """Confirms that BuildStream is installed, so it can be run using subprocess.run"""
    if not shutil.which("bst"):
        # shutil.which will return None, if licensecheck isn't installed
        print(
            "Error, BuildStream does not seem to be installed."
            "(bst_license_checker needs BuildStream to run)",
            file=sys.stderr,
        )
        abort()
