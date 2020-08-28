#! /usr/bin/python3
"""
This project is intended to produce a license-checking utility for BuildStream projects.

The utility will check out the sources of a given element into a temporary folder, run a
license-scanning tool called licensecheck, and then process the
results.
"""

import argparse
import json
import os
from buildstream_license_checker.license_checker import LicenseChecker
from buildstream_license_checker.write_html_output import write_html_output

MACHINE_OUTPUT_FILENAME = "license_check_summary.json"
HUMAN_OUTPUT_FILENAME = "license_check_summary.html"

DESCRIBE_TEXT = """
A license-checking utility for buildstream projects.
Takes a list of buildstream element names and uses "bst show" to generate a list of
those elements' dependencies (see --deps option).
Each dependency is then checked out into a temporary folder, and scanned for license
information. Results are bundled into an output directory, along with human-readable
and machine-readable summary files.
"""
VALID_DEPTYPES = ["none", "run", "all"]


def main():
    """Collect dependency information, run lincensechecks, and output results"""
    # Get arguments
    args = get_args()

    # Create a checker object (abstract class to store script data during execution)
    # and use it to get the results dictionary
    checker = LicenseChecker(
        element_list=args.element_list,
        work_dir=args.work,
        output_dir=args.output,
        depstype=args.deps,
        track_deps=args.track,
        ignorelist_filename=args.ignorelist,
    )
    checker.scan_for_licenses()
    results_dict = checker.get_results()

    # Produce output
    json_output_path = os.path.join(args.output, MACHINE_OUTPUT_FILENAME)
    write_json_output(results_dict, json_output_path)

    html_output_path = os.path.join(args.output, HUMAN_OUTPUT_FILENAME)
    write_html_output(results_dict, html_output_path)


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
    arg_parser.add_argument(
        "-i",
        "--ignorelist",
        required=False,
        metavar="IGNORELIST_FILENAME",
        help=(
            "Filename for a list of elements names to ignore. Ignored elements will not"
            " be fetched, tracked or scanned for licenses. Element names in the ignore"
            " list file should be separated by line breaks (one element name per line)."
            " Lines which start with a hash (#) are treated as comments."
        ),
    )

    return arg_parser.parse_args()


def write_json_output(results_dict, json_output_path):
    """Outputs a json file listing the results. (Simply a wrapper for json.dump.)"""
    with open(json_output_path, mode="w") as outfile:
        json.dump(results_dict, outfile, indent=2)


if __name__ == "__main__":
    main()
