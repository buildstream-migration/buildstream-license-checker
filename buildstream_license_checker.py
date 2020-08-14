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

DESCRIBE_TEXT = f"""
A license-checking utility for buildstream projects.
Takes a list of buildstream element names and uses "bst show" to generate a list of
those elements' dependencies (see --deps option).
Each dependency is then checked out into a temporary folder, and scanned for license
information. Results are bundled into an output directory, along with human-readable
and machine-readable summary files.
"""
VALID_DEPTYPES = ["none", "run", "all"]


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
        self.work_path = prepare_dir(args.work)
        self.output_path = prepare_dir(args.output, needs_empty=True)
        self.depslist = []

    def get_dependencies_from_bst_show(self):
        """Run bst show and extract dependency information"""
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
                DependencyElement(line, self.work_path, self.output_path)
            )

    def track_or_validate_tracking(self):
        """Either track all dependencies, or confirm that tracking isn't needed"""
        if self.track:
            self.track_dependencies()
            # re-initialize list of dependencies, to get correct keys
            self.get_dependencies_from_bst_show()
        else:
            self.confirm_no_tracking_needed()

    def track_dependencies(self):
        """Runs BuildStream's track command to track all dependencies"""
        command_args = ["bst", "track"]
        command_args += [dep.name for dep in self.depslist]

        print("\nRunning bst track command, to track dependencies")
        bst_track_return_code = subprocess.call(command_args)
        if bst_track_return_code != 0:
            print(f"bst track command failed, with exit code {bst_track_return_code}")
            abort()

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
            # if outputfile doesn't exists, create it
            if not os.path.isfile(dep.work_path):
                try:
                    tmp_prefix = f"tmp-checkout--{dep.name.replace('/','-')}"
                    with tempfile.TemporaryDirectory(
                            dir=self.work_path, prefix=tmp_prefix
                    ) as tmpdir:
                        print(f"Checking out source code for {dep.name} in {tmpdir}")
                        dep.checkout_source(tmpdir)

                        print(f"Running license check software for {dep.name}")
                        dep.create_license_raw_output(tmpdir)

                except PermissionError as pmn_error:
                    print(pmn_error)
                    print(
                        "Unable to create directory. Insufficient permissions to"
                        f" create files in {self.work_path}\nPlease check permissions,"
                        " or try a different working directory."
                    )
                    abort()
            shutil.copy(dep.work_path, dep.out_path)


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

        # Assign path attributes
        filename = self.name.replace("/", "-")
        filename += f"--{self.full_key}.licensecheck_output"
        self.work_path = os.path.join(work_dir, filename)
        self.out_path = os.path.join(output_dir, filename)

    def checkout_source(self, checkout_path):
        """Checks out the source-code of a specified element, into a specified
        directory"""
        return_code1 = subprocess.call(
            ["bst", "--colors", "workspace", "open", self.name, checkout_path]
        )
        return_code2 = subprocess.call(["bst", "workspace", "close", self.name])
        if return_code1 != 0 or return_code2 != 0:
            print(f"checking out source code for {self.name} failed")
            abort()

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
    args = get_args()
    checker = BuildStreamLicenseChecker(args)
    checker.get_dependencies_from_bst_show()
    checker.track_or_validate_tracking()
    checker.get_licensecheck_results()


if __name__ == "__main__":
    main()
