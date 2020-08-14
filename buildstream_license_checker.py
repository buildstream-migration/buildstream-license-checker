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

DESCRIBE_TEXT = f"""
A license-checking utility for buildstream projects.
Takes a list of buildstream element names and uses "bst show" to generate a list of
those elements' dependencies (see --deps option).
Each dependency is then checked out into a temporary folder, and scanned for license
information. Results are bundled into an output directory, along with human-readable
and machine-readable summary files.
"""
VALID_DEPTYPES = ["none", "run", "all"]


def abort():
    """Print short message and exit"""
    print("Aborting buildstream-license-checker")
    sys.exit(1)


def main():
    """Collect dependency information, run lincensechecks, and output results"""
    # Parse Arguments
    arg_parser = get_arg_parser()
    args = arg_parser.parse_args()

    # Setup folders
    if args.work == args.output:
        print("ERROR: cannot use same path for output directory and working directory.")
    # prepare_dir returns an absolute path for the directory
    workdir = prepare_dir(args.work)
    outputdir = prepare_dir(args.output, needs_empty=True)

    # Get dependencies
    dependency_list = get_dependencies_from_bst_show(args.deps, args.element_list)

    # Tracking
    if args.track:
        track_dependencies(dependency_list)
        # regenerate dependency_list, since keys may now have updated
        dependency_list = get_dependencies_from_bst_show(args.deps, args.element_list)
    else:
        confirm_track_not_needed(dependency_list)

    # Create raw output files
    # Filenames will be recorded in the dependency dictionaries
    for dep in dependency_list:
        get_licensecheck_results(dep, workdir)


def get_arg_parser():
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

    return arg_parser


def prepare_dir(directory_name, needs_empty=False):
    """Create a needed directory, if it doesn't exist already"""
    directory_name = os.path.abspath(directory_name)
    try:
        os.makedirs(directory_name, exist_ok=True)
    except PermissionError as pmn_error:
        print(pmn_error)
        print(
            "Unable to create directory. Insufficient permissions to create"
            f" {directory_name}"
        )
        print("Please check permissions, or try a different directory path.")
        abort()
    except FileExistsError as fe_error:
        print(fe_error)
        print(
            f"Unable to create directory. {directory_name} already"
            " exists and does not appear to be a directory."
        )
        print("Please delete the existing file, or try a different directory path.")
        abort()
    # test if empty
    if needs_empty:
        if os.listdir(directory_name):
            print(f"ERROR: directory {directory_name} is not empty.")
            abort()
    # directory name was changed by abspath, need to return the new name
    return directory_name


def get_dependencies_from_bst_show(depstype, element_list):
    """Run bst show and extract dependency information"""
    command_args = ["bst", "show", "--deps", depstype]
    command_args += ["--format", "%{name}||%{full-key}||%{state}"]
    command_args += element_list

    print("Running 'bst show' command, to collect list of dependency elements.")
    bst_show_result = subprocess.run(command_args, stdout=subprocess.PIPE, text=True)
    if bst_show_result.returncode != 0:
        print(f"bst show command failed, with exit code {bst_show_result.returncode}")
        abort()

    return_list = []
    bst_show_output = bst_show_result.stdout
    for line in bst_show_output.rstrip().split("\n"):
        line_split = line.rsplit("||", 2)
        return_list.append(
            {"name": line_split[0], "full-key": line_split[1], "state": line_split[2]}
        )
    return return_list


def track_dependencies(dependency_list):
    """Runs BuildStream's track command to track all dependencies"""
    command_args = ["bst", "track"]
    command_args += [dep["name"] for dep in dependency_list]

    print("\nRunning bst track command, to track dependencies")
    bst_track_return_code = subprocess.call(command_args)
    if bst_track_return_code != 0:
        print(f"bst track command failed, with exit code {bst_track_return_code}")
        abort()


def confirm_track_not_needed(dependency_list):
    """Checks whether dependencies need to be tracked. If they do, aborts script."""
    untracked_deps = []
    for dep in dependency_list:
        if dep["state"] == "no reference":
            untracked_deps.append(dep["name"])
    if untracked_deps:
        print("\n\nInconsistent Pipeline")
        print("Refs are missing for the following elements:")
        for dep_name in untracked_deps:
            print("    " + dep_name)
        print("Please track the elements and re-run the script.")
        print('(Alternatively, use the "--track" option to automatically perform')
        print("tracking on all elements and dependencies before they are scanned.)")
        abort()


def get_licensecheck_results(dep, work_dir):
    """Check out dependency sources, and run licensecheck software.
    Save licensecheck output as a file, and collect the filename."""
    # Establish license output filename, and check if it already exists
    dep["license_output_file_path"] = os.path.join(
        work_dir,
        dep["name"].replace("/", "-") + "--" + dep["full-key"] + ".licensecheck_output",
    )
    # if the output file already exists (with the correct hash key), then skip the rest
    if os.path.isfile(dep["license_output_file_path"]):
        return
    # otherwise:
    try:
        tmp_prefix = f"tmp-checkout--{dep['name'].replace('/','-')}"
        with tempfile.TemporaryDirectory(dir=work_dir, prefix=tmp_prefix) as tmpdir:
            checkout_path = os.path.abspath(tmpdir)

            print(f"Checking out source code for {dep['name']} in {tmpdir}")
            checkout_source(dep["name"], checkout_path)

            print(f"Running license check software for {dep['name']}")
            create_license_raw_output(
                filepath=dep["license_output_file_path"], checkout_path=checkout_path
            )
    except PermissionError as pmn_error:
        print(pmn_error)
        print(
            "Unable to create directory. Insufficient permissions to create files"
            f" in {work_dir}"
        )
        print("Please check permissions, or try a different working directory.")
        abort()


def checkout_source(dep_name, checkout_path):
    """Checks out the source-code of a specified element, into a specified directory"""
    return_code1 = subprocess.call(
        ["bst", "--colors", "workspace", "open", dep_name, checkout_path]
    )
    return_code2 = subprocess.call(["bst", "workspace", "close", dep_name])
    if return_code1 != 0 or return_code2 != 0:
        print(f"checking out source code for {dep_name} failed")
        abort()


def create_license_raw_output(filepath, checkout_path):
    """Runs the actual license-checking software, to collect licenses from a specified
    directory"""
    with open(filepath, mode="w") as outfile:
        return_code = subprocess.call(
            ["licensecheck", "-mr", "."], cwd=checkout_path, stdout=outfile
        )
    if return_code != 0:
        print(f"Running licensecheck failed for {filepath}")
        abort()


if __name__ == "__main__":
    main()
