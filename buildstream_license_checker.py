#! /usr/bin/python3
"""
This project is intended to produce a license-checking utility for BuildStream projects.

The utility will check out the sources of a given element into a temporary folder, run a
license-scanning tool called licensecheck, and then process the
results.
"""

import argparse
import os.path
import sys
import subprocess
import tempfile
import shutil
import json
from enum import Enum

DESCRIBE_TEXT = f"""
A license-checking utility for buildstream projects.
Takes a list of buildstream element names and uses "bst show" to generate a list of
those elements' dependencies (see --deps option).
Each dependency is then checked out into a temporary folder, and scanned for license
information. Results are bundled into an output directory, along with human-readable
and machine-readable summary files.
"""
VALID_DEPTYPES = ["none", "run", "all"]
INVALID_LICENSE_VALUES = {
    "",
    "UNKNOWN",
    "GENERATED FILE",
    "*No copyright* UNKNOWN",
    "*No copyright* GENERATED FILE",
}


class CheckoutStatus(Enum):
    """Checkout Status"""

    none = None
    fetch_failed = "fetch failed"
    checkout_failed = "checkout failed"
    checkout_succeeded = "checkout succeeded"


def get_args():
    """Prepare the arg_parser object."""
    arg_parser = argparse.ArgumentParser(description=DESCRIBE_TEXT)

    arg_parser.add_argument(
        "element_list",
        nargs="+",
        metavar="ELEMENT_NAMES",
        help="One or more elements to be checked.",
    )
    default_depstype = "run"
    arg_parser.add_argument(
        "-d",
        "--deps",
        default=default_depstype,
        metavar="DEPS_TYPE",
        choices=VALID_DEPTYPES,
        help=(
            "The type of dependencies to scan. Will be passed directly to the"
            " 'bst show' command. Choose from: "
        )
        + ", ".join(VALID_DEPTYPES)
        + f". Defaults to: {default_depstype}.",
    )
    arg_parser.add_argument(
        "-t",
        "--track",
        action="store_true",
        help="Run the bst track command on each dependency before checking.",
    )
    arg_parser.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="OUTPUT_DIRECTORY",
        help=(
            "The path to an output directory, in which to store license results. Will"
            " be created if it doesn't already exist. Directory must be empty."
        ),
    )
    arg_parser.add_argument(
        "-w",
        "--work",
        required=True,
        metavar="WORKING_DIRECTORY",
        help=(
            "License results will be created here first, and saved. Can be reused (does"
            " not need to be emptied between invocations). Can be used as a cache:"
            " previously processed results will be reused if the hash-key has not"
            " changed."
        ),
    )

    return arg_parser.parse_args()


class BuildStreamLicenseChecker:
    """Abstract class to contain all the important data"""

    def __init__(self, args):
        self.element_list = args.element_list
        self.deps_type = args.deps
        self.track = args.track
        self.work_dir = prepare_dir(args.work)
        self.output_dir = prepare_dir(args.output, needs_empty=True)
        self.depslist = []

    def get_dependencies_from_bst_show(self):
        """Run bst show and extract dependency information.
        Note that running the function again will update all the bst-show information,
        (names, keys, and statuses) and delete any license-scan results."""
        # reinitialize
        self.depslist = []

        # call bst show
        print("Running 'bst show' command, to collect list of dependency elements.")
        command_args = ["bst", "show", "--deps", self.deps_type]
        command_args += ["--format", "%{name}||%{full-key}||%{state}"]
        command_args += self.element_list
        bst_show_result = subprocess.run(
            command_args, stdout=subprocess.PIPE, text=True
        )
        if bst_show_result.returncode != 0:
            print(
                f"bst show command failed, with exit code {bst_show_result.returncode}"
            )
            abort()

        # process output
        bst_show_output = bst_show_result.stdout
        for line in bst_show_output.rstrip().split("\n"):
            self.depslist.append(
                DependencyElement(line, self.work_dir, self.output_dir)
            )

    def fetch_and_track(self):
        """Either track all dependencies, or confirm that tracking isn't needed, then
        run bst fetch on all dependencies. Finally, rerun bst show to collect the
        updated output.
        Note that this function can leave the dependency list out of date. Therefore it
        should be followed by another call to get_dependencies.from_bst_show()
        (to update the dependency list with the new keys and new statuses).
        """
        # First, produce a list of all dependencies by name, suitable for supplying to
        # subprocess.call()
        depnames = [dep.name for dep in self.depslist]
        # Either track all dependencies, or confirm that tracking isn't needed
        if self.track:
            self.track_dependencies(depnames)
        else:
            self.confirm_no_tracking_needed()
        # Attempt bst fetch on all dependencies
        self.fetch_sources(depnames)
        # Note: this function is intended to update refs and changes the status of
        # date with the new full-keys and new statuses.

    def track_dependencies(self, depnames_list):
        """Runs BuildStream's track command to track all dependencies"""
        command_args = ["bst", "track"]
        command_args += depnames_list

        print("\nRunning bst track command, to track dependencies")
        bst_track_return_code = subprocess.call(command_args)
        if bst_track_return_code != 0:
            print(f"bst track command failed, with exit code {bst_track_return_code}")
            abort()

    def fetch_sources(self, depnames_list):
        """Runs Buildstream's fetch command to confirm that that sources are correctly
        fetched. (Fetch will fail for elements whith sources which are unavailable,
        But elements with no sources will fetch successfully with no error)."""
        command_args = ["bst", "--on-error", "continue", "fetch", "--deps", "none"]
        command_args += depnames_list
        print("\nRunning bst fetch command, to fetch sources")
        subprocess.call(command_args)
        # No need to check return code. Failures will be recognized by their
        # status in bst show results.

    def confirm_no_tracking_needed(self):
        """Checks whether dependencies need to be tracked. If they do, aborts script."""
        untracked_deps = [
            dep.name for dep in self.depslist if dep.state == "no reference"
        ]
        if untracked_deps:
            print("\n\nInconsistent Pipeline")
            print("Refs are missing for the following elements:")
            for dep_name in untracked_deps:
                print("    " + dep_name)
            print("Please track the elements and re-run the script.")
            print('(Alternatively, use the "--track" option to automatically perform')
            print("tracking on all elements and dependencies before they are scanned.)")
            abort()

    def get_licensecheck_results(self):
        """Check out dependency sources, and run licensecheck software.
        Save licensecheck output as a file in workdir, and copy file to outputdir."""
        for dep in self.depslist:
            dep.get_licensecheck_result(self.work_dir)

    def update_license_lists(self):
        """Iterates through dependencies, to read their licensecheck output files and
        update their "license_outputs" attribute."""
        for dep in self.depslist:
            dep.update_license_list()

    def output_summary_machine_readable(self):
        """Outputs a machine_readable summary of the dependencies and their licenses"""
        machine_output_filename = os.path.join(
            self.output_dir, "license_check_summary.json"
        )
        with open(machine_output_filename, mode="w") as outfile:
            json.dump([dep.dict() for dep in self.depslist], outfile, indent=2)


class DependencyElement:
    """A dependency element, with all the data determined from bst show"""

    def __init__(self, bst_show_line, work_dir, output_dir):
        # If the input line was generated by BuildStreamLicenseChecker's
        # getdependencies_from_bst_show() method, then it will be in the format
        # "%{name}||%{full-key}||%{state}"

        # Assign simple attributes
        line_split = bst_show_line.rsplit("||", 2)
        self.name = line_split[0]
        self.full_key = line_split[1]
        self.state = line_split[2]
        self.checkout_status = CheckoutStatus.none

        # Assign path attributes
        filename = self.name.replace("/", "-")
        filename += f"--{self.full_key}.licensecheck_output"
        self.work_path = os.path.join(work_dir, filename)
        self.out_path = os.path.join(output_dir, filename)

        # Prepare for final summary
        self.license_outputs = set()

    def get_licensecheck_result(self, work_dir):
        """Check out dependency sources, and run licensecheck software.
        Save licensecheck output as a file in workdir, and copy file to outputdir."""
        # if output file already exists, update checkout_status and do nothing else
        if os.path.isfile(self.work_path):
            self.checkout_status = CheckoutStatus.checkout_succeeded
            shutil.copy(self.work_path, self.out_path)
        # if fetch still needed, assume that 'fetch' has already failed, and don't
        # bother attempting to check out sources
        elif self.state == "fetch needed":
            self.checkout_status = CheckoutStatus.fetch_failed
        # otherwise, since outputfile doesn't exist, try to create it
        else:
            try:
                tmp_prefix = f"tmp-checkout--{self.name.replace('/','-')}"
                with tempfile.TemporaryDirectory(
                    dir=work_dir, prefix=tmp_prefix
                ) as tmpdir:
                    print(f"Checking out source code for {self.name} in {tmpdir}")
                    self.checkout_source(tmpdir)

                    print(f"Running license check software for {self.name}")
                    self.create_license_raw_output(tmpdir)
                    shutil.copy(self.work_path, self.out_path)

            except PermissionError as pmn_error:
                print(pmn_error)
                print(
                    "Unable to create directory. Insufficient permissions to"
                    f" create files in {work_dir}\nPlease check permissions,"
                    " or try a different working directory."
                )
                abort()

    def checkout_source(self, checkout_path):
        """Checks out the source-code of a specified element, into a specified
        directory"""
        return_code = subprocess.call(
            ["bst", "--colors", "workspace", "open", self.name, checkout_path]
        )
        if return_code == 0:
            self.checkout_status = (
                CheckoutStatus.checkout_succeeded
                if return_code == 0
                else CheckoutStatus.checkout_failed
            )
        subprocess.call(["bst", "workspace", "close", self.name])
        # (no need to check return code for 'bst workspace close'. Script should
        # proceed in the same way whether it fails or not)

    def create_license_raw_output(self, checkout_path):
        """Runs the actual license-checking software, to collect licenses from a
        specified directory"""
        partfile_name = self.work_path + "-partial"
        with open(partfile_name, mode="w") as outfile:
            return_code = subprocess.call(
                ["licensecheck", "-mr", "."], cwd=checkout_path, stdout=outfile
            )
        if return_code != 0:
            print(f"Running licensecheck failed for {self.work_path}")
            abort()
        os.rename(partfile_name, self.work_path)

    def dict(self):
        """Returns a dictionary with the key information about the dependency"""
        return {
            "dependency name": self.name,
            "dependency full_key": self.full_key,
            "checkout status": self.checkout_status.value,
            "licensecheck_output": sorted(list(self.license_outputs)),
        }

    def update_license_list(self):
        """Reads the licensecheck output files, and updates the license_outputs
        attribute"""

        def stripline(line):
            line = line.rsplit("\t", 2)[1]
            line = line.replace("GENERATED FILE", "")
            line = line.strip()
            return line

        if os.path.isfile(self.work_path):
            with open(self.work_path, mode="r") as openfile:
                self.license_outputs = {stripline(line) for line in openfile}

            self.license_outputs.difference_update(INVALID_LICENSE_VALUES)


def prepare_dir(directory_name, needs_empty=False):
    """Create a needed directory, if it doesn't exist already"""
    directory_path = os.path.abspath(directory_name)
    try:
        os.makedirs(directory_path, exist_ok=True)
    except PermissionError as pmn_error:
        print(pmn_error)
        print(
            "Unable to create directory. Insufficient permissions to create"
            f" {directory_path}"
        )
        print("Please check permissions, or try a different directory path.")
        abort()
    except FileExistsError as fe_error:
        print(fe_error)
        print(
            f"Unable to create directory. {directory_path} already"
            " exists and does not appear to be a directory."
        )
        print("Please delete the existing file, or try a different directory path.")
        abort()
    # test if empty
    if needs_empty:
        if os.listdir(directory_path):
            print(f"ERROR: directory {directory_path} is not empty.")
            abort()
    # return the absolute path to the directory
    return directory_path


def abort():
    """Print short message and exit"""
    print("Aborting buildstream-license-checker")
    sys.exit(1)


def main():
    """Collect dependency information, run lincensechecks, and output results"""
    # Get arguments
    args = get_args()

    # Create a checker object (abstract class to store script data during execution)
    checker = BuildStreamLicenseChecker(args)

    # Gather dependency names, keys, and statuses
    checker.get_dependencies_from_bst_show()

    # Track elements (if user requests) and fetch sources
    checker.fetch_and_track()

    # Generate bst show output again, since keys and statuses may have changed
    checker.get_dependencies_from_bst_show()

    # Check out sources and run license scan for each element
    checker.get_licensecheck_results()
    checker.update_license_lists()
    checker.output_summary_machine_readable()


if __name__ == "__main__":
    main()
