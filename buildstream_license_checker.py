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
    arg_parser = get_arg_parser()
    args = arg_parser.parse_args()

    if args.work == args.output:
        print("ERROR: cannot use same path for output directory and working directory.")
    prepare_dir(args.work)
    prepare_dir(args.output, needs_empty=True)

    print(f"elements: " + ", ".join(args.element_list))


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
            f" {directory_name}."
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


if __name__ == "__main__":
    main()
