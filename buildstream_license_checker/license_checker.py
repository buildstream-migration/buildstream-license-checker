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
LicenseChecker
==============

The LicenseChecker class is responsible for perfoming the main operation of
bst_license_checker: checking out source code for multiple elements and collecting
license scan results.

A LicenseChecker object stores the relevant arguments supplied to the script, and runs
the bst show, bst track, and bst fetch commands as needed, identifying the relevant list
of dependency elements which must be scanned. The object also stores the summary results
from each license scan, and returns them as a single dictionary to be processed into the
human readable and machine-readable outputs.

The actual operation of checking out the source code and scanning for licenses is
delegated to the DependencyElement class, each instance of which operates on a single
element.
"""

import os.path
import subprocess
from buildstream_license_checker.dependency_element import DependencyElement
from buildstream_license_checker.utils import abort, echo
from buildstream_license_checker.utils import confirm_scanning_software_installed
from buildstream_license_checker.buildstream_commands import bst_track_dependencies
from buildstream_license_checker.buildstream_commands import bst_fetch_sources


class LicenseChecker:
    """Abstract class to perform a license scan and to store and return scan results"""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        element_list,
        work_dir,
        output_dir,
        depstype="run",
        track_deps=False,
        ignorelist_filename=None,
    ):
        confirm_scanning_software_installed()

        self.element_list = element_list
        self.depslist = []
        self.work_dir = prepare_dir(work_dir)
        self.output_dir = prepare_dir(output_dir, needs_empty=True)

        self.depstype = depstype
        self.track_deps = track_deps

        self.ignorelist = []
        if ignorelist_filename:
            with open(ignorelist_filename, mode="r") as ignorelist_file:
                # take each line from the ignore list, strip trailing linebreaks
                # unless the line starts with a hash. (Treated as comments)
                self.ignorelist = [
                    line.rstrip("\n")
                    for line in ignorelist_file
                    if not line.startswith("#")
                ]

    def scan_for_licenses(self):
        """Fetches and checks out source code, and scans each element for licenses
        Creates an output file with a full license scan result for each element,
        and updates the all the DependencyElement objects with a summary list of all
        licenses found"""

        # Gather dependency names, keys, and statuses
        self.get_dependencies_from_bst_show()
        # Track elements (if user requests) and fetch sources
        self.track_and_fetch()
        # Generate bst show output again, since keys and statuses may have changed
        self.get_dependencies_from_bst_show()

        # Check out sources and run license scan for each element
        for dep in self.depslist:
            dep.get_licensecheck_result(self.work_dir)
            dep.update_license_list()

    def get_results(self):
        """Returns a dictionary containing a breakdown of licenses found, by element."""
        licenses_detected = []
        for dep in self.depslist:
            # get list of all licenses:
            dep_dict = dep.get_dict()
            licenses_detected.append(dep_dict)
        return {"dependency-list": licenses_detected}

    def get_dependencies_from_bst_show(self):
        """Run bst show and extract dependency information.
        Note that running the function again will update all the bst-show information,
        (names, keys, and statuses) and delete any license-scan results."""
        # reinitialize
        self.depslist = []

        # call bst show
        echo("Running 'bst show' command to collect list of dependency elements.")
        command_args = ["bst", "show", "--deps", self.depstype]
        command_args += ["--format", "%{name}||%{full-key}||%{state}"]
        command_args += self.element_list
        bst_show_result = subprocess.run(
            command_args, stdout=subprocess.PIPE, text=True
        )
        if bst_show_result.returncode != 0:
            echo(f"bst show command failed with exit code {bst_show_result.returncode}")
            abort()

        # process output
        bst_show_output = bst_show_result.stdout
        for line in bst_show_output.rstrip().split("\n"):
            dep = DependencyElement(line, self.work_dir, self.output_dir)
            if dep.name not in self.ignorelist:
                self.depslist.append(dep)
        self.depslist.sort()

    def track_and_fetch(self):
        """Either track all dependencies, or confirm that tracking isn't needed, then
        run bst fetch on all dependencies. Finally, rerun bst show to collect the
        updated output.
        Note that this function can leave the dependency list out of date. Therefore it
        should be followed by another call to get_dependencies.from_bst_show()
        (to update the dependency list with the new keys and new statuses).
        """

        # First, produce a list of all dependencies by name, suitable for supplying to
        # subprocess.call()
        depnames = tuple(dep.name for dep in self.depslist)
        # Either track all dependencies, or confirm that tracking isn't needed
        if self.track_deps:
            bst_track_return_code = bst_track_dependencies(depnames)
            if bst_track_return_code != 0:
                echo(f"bst track command failed with exit code {bst_track_return_code}")
                abort()
        else:
            self.confirm_no_tracking_needed()
        # Attempt bst fetch on all dependencies
        bst_fetch_sources(depnames)
        # Note: this function is intended to update refs and change the status of
        # dependencies. After running this function, it is important to run
        # get_dependencies_from_bst_show() again, to update with the new full-keys
        # and new statuses.

    def confirm_no_tracking_needed(self):
        """Checks whether dependencies need to be tracked. If they do, aborts script."""
        untracked_deps = [
            dep.name for dep in self.depslist if dep.state == "no reference"
        ]
        if untracked_deps:
            echo("\n\nInconsistent Pipeline")
            echo("Refs are missing for the following elements:")
            for dep_name in untracked_deps:
                echo(f"\t{dep_name}")
            echo("Please track the elements and re-run the script.")
            echo('(Alternatively, use the "--track" option to automatically perform')
            echo("tracking on all elements and dependencies before they are scanned.)")
            abort()


def prepare_dir(directory_name, needs_empty=False):
    """Create a needed directory, if it doesn't exist already"""
    directory_path = os.path.abspath(directory_name)
    try:
        os.makedirs(directory_path, exist_ok=True)
    except PermissionError as pmn_error:
        echo(pmn_error)
        echo("Unable to create directory.")
        echo(f"Insufficient permissions to create {directory_path}")
        echo("Please check permissions, or try a different directory path.")
        abort()
    except FileExistsError as fe_error:
        echo(fe_error)
        echo(f"Unable to create directory.")
        echo("{directory_path} already exists and does not appear to be a directory.")
        echo("Please delete the existing file, or try a different directory path.")
        abort()
    # test if empty
    if needs_empty:
        if os.listdir(directory_path):
            echo(f"ERROR: directory {directory_path} is not empty.")
            abort()
    # return the absolute path to the directory
    return directory_path
