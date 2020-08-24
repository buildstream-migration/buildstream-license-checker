#! /usr/bin/python3
"""Contains the LicenseChecker class, as used by the bst_license_checker script.
The LicenseChecker class stores the relevant arugments supplied to the script, and the
methods for extracting license information. (Except for those methods delegated to the
DependencyElement class).
The LicenseChecker object also stores and returns a dictionary containing the results of
the license scan."""

import os.path
import subprocess
import sys
import re
from dependency_element import DependencyElement
from dependency_element import abort

MACHINE_OUTPUT_FILENAME = "license_check_summary.json"
HUMAN_OUTPUT_FILENAME = "license_check_summary.html"


class LicenseChecker:
    """Abstract class to scan contain data for license-scanning"""

    def __init__(self, args):
        self.args = args
        self.work_dir = prepare_dir(args.work)
        self.output_dir = prepare_dir(args.output, needs_empty=True)
        self.depslist = []
        self.blacklist = []

        if args.blacklist:
            with open(args.blacklist, mode="r") as blacklist_file:
                # take each line from the blacklist file, and strip trailing linebreaks
                # then compile each line as a regular expression
                # unless the line starts with a hash. (Treated as comments)
                self.blacklist = [
                    re.compile(line.rstrip("\n"))
                    for line in blacklist_file
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
        """Returns a dictionary containing a breakdown of licenses found, by element.
        Also generates a report of any blacklisted licenses that have been found, and
        includes this in the results dictionary."""
        licenses_detected = []
        blacklist_violations = {}
        for dep in self.depslist:
            # get list of all licenses:
            dep_dict = dep.get_dict()
            licenses_detected.append(dep_dict)

            # get blacklist_violations
            if self.blacklist:
                violations = []
                for license_string in dep_dict["licensecheck output"]:
                    for license_expression in self.blacklist:
                        if license_expression.search(license_string):
                            violations += [license_string]
                            break
                if violations:
                    blacklist_violations.update(
                        {dep_dict["dependency name"], violations}
                    )
        return {
            "blacklist violations": blacklist_violations,
            "licenses detected": licenses_detected,
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
        command_args = ["bst", "show", "--deps", self.args.deps]
        command_args += ["--format", "%{name}||%{full-key}||%{state}"]
        command_args += self.args.element_list
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
            self.depslist.append(
                DependencyElement(line, self.work_dir, self.output_dir)
            )
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
        if self.args.track:
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
