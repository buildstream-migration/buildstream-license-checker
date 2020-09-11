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
import sys
from buildstream_license_checker.dependency_element import DependencyElement
from buildstream_license_checker.dependency_element import abort

MACHINE_OUTPUT_FILENAME = "license_check_summary.json"
HUMAN_OUTPUT_FILENAME = "license_check_summary.html"


class LicenseChecker:
    """Abstract class to scan contain data for license-scanning"""

    def __init__(
            self,
            element_list,
            work_dir,
            output_dir,
            depstype="run",
            track_deps=False,
            ignorelist_filename=None,
    ):
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
        return {
            "dependency-list": licenses_detected,
        }

    def get_dependencies_from_bst_show(self):
        """Run bst show and extract dependency information.
        Note that running the function again will update all the bst-show information,
        (names, keys, and statuses) and delete any license-scan results."""
        # reinitialize
        self.depslist = []

        # call bst show
        print(
            "Running 'bst show' command, to collect list of dependency elements.",
            file=sys.stderr,
        )
        command_args = ["bst", "show", "--deps", self.depstype]
        command_args += ["--format", "%{name}||%{full-key}||%{state}"]
        command_args += self.element_list
        bst_show_result = subprocess.run(
            command_args, stdout=subprocess.PIPE, text=True
        )
        if bst_show_result.returncode != 0:
            print(
                f"bst show command failed, with exit code {bst_show_result.returncode}",
                file=sys.stderr,
            )
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

        def track_dependencies(depnames_list):
            """Runs BuildStream's track command to track all dependencies"""
            command_args = ["bst", "track"]
            command_args += depnames_list

            print("\nRunning bst track command, to track dependencies", file=sys.stderr)
            bst_track_return_code = subprocess.call(command_args)
            if bst_track_return_code != 0:
                print(
                    f"bst track command failed, with exit code {bst_track_return_code}",
                    file=sys.stderr,
                )
                abort()

        def fetch_sources(depnames_list):
            """Runs Buildstream's fetch command to confirm that that sources are
            correctly fetched. (Fetch will fail for elements with sources which are
            unavailable, But elements with no sources will fetch successfully with no
            error)."""
            command_args = ["bst", "--on-error", "continue", "fetch", "--deps", "none"]
            command_args += depnames_list
            print("\nRunning bst fetch command, to fetch sources", file=sys.stderr)
            subprocess.call(command_args)
            # No need to check return code. Failures will be recognized by their
            # status in bst show results.

        # First, produce a list of all dependencies by name, suitable for supplying to
        # subprocess.call()
        depnames = [dep.name for dep in self.depslist]
        # Either track all dependencies, or confirm that tracking isn't needed
        if self.track_deps:
            track_dependencies(depnames)
        else:
            self.confirm_no_tracking_needed()
        # Attempt bst fetch on all dependencies
        fetch_sources(depnames)
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
            print("\n\nInconsistent Pipeline", file=sys.stderr)
            print("Refs are missing for the following elements:", file=sys.stderr)
            for dep_name in untracked_deps:
                print("    " + dep_name, file=sys.stderr)
            print("Please track the elements and re-run the script.", file=sys.stderr)
            print(
                '(Alternatively, use the "--track" option to automatically perform',
                file=sys.stderr,
            )
            print(
                "tracking on all elements and dependencies before they are scanned.)",
                file=sys.stderr,
            )
            abort()


def prepare_dir(directory_name, needs_empty=False):
    """Create a needed directory, if it doesn't exist already"""
    directory_path = os.path.abspath(directory_name)
    try:
        os.makedirs(directory_path, exist_ok=True)
    except PermissionError as pmn_error:
        print(pmn_error, file=sys.stderr)
        print(
            "Unable to create directory. Insufficient permissions to create"
            f" {directory_path}",
            file=sys.stderr,
        )
        print(
            "Please check permissions, or try a different directory path.",
            file=sys.stderr,
        )
        abort()
    except FileExistsError as fe_error:
        print(fe_error, file=sys.stderr)
        print(
            f"Unable to create directory. {directory_path} already"
            " exists and does not appear to be a directory.",
            file=sys.stderr,
        )
        print(
            "Please delete the existing file, or try a different directory path.",
            file=sys.stderr,
        )
        abort()
    # test if empty
    if needs_empty:
        if os.listdir(directory_path):
            print(f"ERROR: directory {directory_path} is not empty.", file=sys.stderr)
            abort()
    # return the absolute path to the directory
    return directory_path
