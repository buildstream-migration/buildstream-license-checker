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
from license_checker import LicenseChecker
from dependency_element import CheckoutStatus

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
    checker = LicenseChecker(args)
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


def write_html_output(results_dict, html_output_path):
    """Outputs a human readable html file listing the license scan results."""
    html_blacklist_results = ""
    html_dependencies = ""

    # get html for dependencies
    for dep in results_dict["licenses detected"]:
        # basic info for each dependency
        dep_start = DEP_HTML_START.format(
            dependency_name=dep["dependency name"],
            dependency_checkout_status=dep["checkout status"],
            full_key_1=dep["full key"][:32],
            full_key_2=dep["full key"][32:],
        )

        # licensecheck results
        dep_middle = ""
        if dep["checkout status"] == CheckoutStatus.checkout_succeeded.value:
            dep_middle += LICENSE_HTML_START.format(
                output_basename=dep["output_filename"]
            )
            for license_line in dep["licensecheck output"]:
                dep_middle += LICENSE_HTML_LINE.format(license_line=license_line)
            dep_middle += LICENSE_HTML_END
        elif dep["checkout status"] == CheckoutStatus.checkout_failed.value:
            dep_middle += CHECKOUT_FAILED_HTML
        elif dep["checkout status"] == CheckoutStatus.fetch_failed.value:
            dep_middle += FETCH_FAILED_HTML

        # pull all the info together (for each dependency)
        html_dependencies += dep_start
        html_dependencies += dep_middle
        html_dependencies += DEP_HTML_END

    # write html to output file
    with open(html_output_path, mode="w") as outfile:
        outfile.write(HTML_START)
        outfile.write(html_blacklist_results)
        outfile.write(html_dependencies)
        outfile.write(HTML_END)


HTML_START = """<!DOCTYPE html>
<html>
<head>
<title>BuildStream license checker - Results Summary</title>
</head>
<style>
.dependency {
  margin: 1em;
  border-width: thin;
  border-style: solid;
}
.dep_fields {
  border-bottom-width: thin;
  border-bottom-style: solid;
  padding: 5px;
}
.licensecheck_output {
  padding: 5px;
}
.license_list {
  column-count: 2
}
.license_item {
  break-inside: avoid
}
</style>
"""

HTML_END = """
</body>
</html>
"""

DEP_HTML_START = """
  <div class="dependency">
    <div class="dep_fields">
      <table>
        <tr><td><strong>Name:</strong></td><td>{dependency_name}</td></tr>
        <tr><td><strong>Checkout:</strong></td><td>{dependency_checkout_status}</td></tr>
        <tr><td><strong>Full&nbsp;Key:</strong></td><td>{full_key_1}<wbr>{full_key_2}</td></tr>
      </table>
    </div>
    <div class="licensecheck_output">
"""

DEP_HTML_END = """
    </div>
  </div>
"""

LICENSE_HTML_START = """
      <strong>Licences: </strong><br>
      <a href="{output_basename}" title="See the detailed license scan output.">(see full output)</a>
      <ul class="license_list">
"""

LICENSE_HTML_LINE = """        <li class="license_item">{license_line}</li>"""

LICENSE_HTML_END = """      </ul>"""

CHECKOUT_FAILED_HTML = """
<strong>NO RESULTS:</strong> No sources checked out.
<p style="max-width: 45em;"><small> The script was unable to check out any sources for this element.
If the element does not have any sources (eg a stack element, or a filter element)
then this is the expected result. Otherwise, this result may mean there has been an
error.</small></p>
"""

FETCH_FAILED_HTML = """
<strong>NO RESULTS:</strong> 'bst fetch' command failed.
<p style="max-width: 45em;"><small> BuildStream's fetch command was unable to fetch
sources for this element. This could mean that there is an error in the element
(such a mistake in the source URL), or it could mean that an external resource is not
currently available for download.</small></p>
"""

if __name__ == "__main__":
    main()
