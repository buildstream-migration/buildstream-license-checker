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
Set BuildStream Commands
========================

Contains the functions which invoke BuildStream commands.
Autodetects the currently-installed version of BuildStream and
uses the appropriate commands for the version.
"""

import os
import subprocess
import sys
from buildstream_license_checker.utils import (
    abort,
    CheckoutStatus,
    confirm_buildstream_installed,
)

confirm_buildstream_installed()


def get_version():
    """Gets the BuildStream version, using subprocess and 'bst --version'.
    Returns a tuple with Major version number and Minor version number"""
    result_obj = subprocess.run(["bst", "--version"], stdout=subprocess.PIPE, text=True)
    version_text = result_obj.stdout.strip()
    try:
        versions = version_text.split(".")
        major = int(versions[0])
        minor = int(versions[1])
    except (IndexError, ValueError, AttributeError):
        print(f"Malformed version string: {version_text}.", file=sys.stderr)
        abort()
    return major, minor


def bst_checkout_v1(element_name, checkout_base_path):
    """Checks out the source-code of a specified element, into a specified
    directory (for bst version 1.4.X, tested with 1.4.3)"""
    return_code = subprocess.call(
        ["bst", "--colors", "workspace", "open", element_name, checkout_base_path]
    )
    subprocess.call(["bst", "workspace", "close", element_name])
    if return_code != 0:
        # there was an error in checkout. Return "None" to signal failure.
        return CheckoutStatus.checkout_failed, None
    # otherwise return the checkout path
    # this process checks out files directly in the checkout base path
    return CheckoutStatus.checkout_succeeded, checkout_base_path


def bst_checkout_v2(element_name, checkout_base_path):
    """Checks out the source-code of a specified element, into a specified
    directory (for bst versions 1.9X.X, tested with 1.93.4)"""
    return_code = subprocess.call(
        [
            "bst",
            "source",
            "checkout",
            "--deps",
            "none",
            element_name,
            "--directory",
            checkout_base_path,
        ]
    )
    if return_code != 0:
        # there was an error in checkout.
        return CheckoutStatus.checkout_failed, None
    checkout_dir_contents = os.listdir(checkout_base_path)
    if not checkout_dir_contents:
        # If bst source checkout succeeded, but the checkout dir is empty:
        return CheckoutStatus.no_sources, None
    # otherwise, report a succesful checkout, and return the source directory
    # (which is a new folder, created inside the checkout_base_path directory)
    new_dir_path = os.path.join(checkout_base_path, checkout_dir_contents[0])
    return CheckoutStatus.checkout_succeeded, new_dir_path


## set version-dependant variables ##

MAJOR_VERSION, MINOR_VERSION = get_version()
if MAJOR_VERSION == 1 and MINOR_VERSION < 90:
    # tested with version 1.4.3
    BST_CHECKOUT_FUNCTION = bst_checkout_v1
    BST_TRACK_COMMANDS = ("bst", "track", "--deps", "none")
    BST_FETCH_COMMANDS = ("bst", "--on-error", "continue", "fetch", "--deps", "none")
elif (MAJOR_VERSION == 1 and MINOR_VERSION >= 93) or MAJOR_VERSION == 2:
    # tested with version 1.93.4
    BST_CHECKOUT_FUNCTION = bst_checkout_v2
    BST_TRACK_COMMANDS = ("bst", "source", "track", "--deps", "none")
    BST_FETCH_COMMANDS = ("bst", "--on-error", "continue")
    BST_FETCH_COMMANDS += ("source", "fetch", "--deps", "none")
else:
    print(
        f"BuildStream version not supported: {MAJOR_VERSION}.{MINOR_VERSION}",
        file=sys.stderr,
    )
    abort()


def bst_checkout(element_name, checkout_base_path):
    """Checks out the source-code of a specified element, into a specified
    directory (wrapper function for calling version-specific checkout functions)"""
    return BST_CHECKOUT_FUNCTION(element_name, checkout_base_path)


def bst_track_dependencies(depnames):
    """Runs BuildStream's track command to track all dependencies"""
    print("\nRunning bst track command to track dependencies", file=sys.stderr)
    command_args = BST_TRACK_COMMANDS + depnames
    bst_track_return_code = subprocess.call(command_args)
    return bst_track_return_code


def bst_fetch_sources(depnames):
    """Runs Buildstream's fetch command to confirm that that sources are
    correctly fetched. (Fetch will fail for elements with sources which are
    unavailable, But elements with no sources will fetch successfully with no
    error)."""
    print("\nRunning bst fetch command, to fetch sources", file=sys.stderr)
    command_args = BST_FETCH_COMMANDS + depnames
    subprocess.call(command_args)
    # No need to check return code. Failures will be recognized by their
    # status in bst show results.
