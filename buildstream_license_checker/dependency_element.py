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
DependencyElement
=================

A DependencyElement object stores information about exactly one buildstream element,
and has the methods to extract and return license information for that one element.
"""

import os.path
import shutil
import subprocess
import sys
import tempfile
from buildstream_license_checker.utils import abort, CheckoutStatus, echo
from buildstream_license_checker.buildstream_commands import bst_checkout

INVALID_LICENSE_VALUES = {
    "",
    "UNKNOWN",
    "GENERATED FILE",
    "*No copyright* UNKNOWN",
    "*No copyright* GENERATED FILE",
}


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
        filename += f"--{self.full_key}.licensecheck_output.txt"
        self.work_path = os.path.join(work_dir, filename)
        self.out_path = os.path.join(output_dir, filename)

        # Prepare for final summary
        self.license_outputs = set()

    def __lt__(self, other):
        return self.name < other.name

    def get_licensecheck_result(self, work_dir):
        """Check out dependency sources, and run licensecheck software.
        Save licensecheck output as a file in workdir, and copy file to outputdir."""
        # if output file already exists in the working directory and has the correct
        # full-key, then we know that the source hasn't changed since the last license
        # scan, and we can re-use the cached file.

        # (Exception: if an element's full-key is represented as a string of question
        # marks it means that the proper full-key is unknown (usually because not all
        # of the element's build dependencies have been tracked). In that scenario we
        # can't use the cached file, because we cannot know whether the source has
        # changed since the last license scan.)

        if os.path.isfile(self.work_path) and "????" not in self.full_key:
            # update checkout_status and do nothing else
            echo(
                f"Skipping license scan for {self.name}. \tFound results from previous"
                " scan in working directory."
            )
            self.checkout_status = CheckoutStatus.checkout_succeeded
            shutil.copy(self.work_path, self.out_path)

        # if we don't have an existing file and fetch is still needed, assume that
        # 'bst fetch' has already failed, and don't attempt to check out sources
        elif self.state == "fetch needed":
            self.checkout_status = CheckoutStatus.fetch_failed

        # otherwise, since outputfile doesn't exist, try to create it
        else:
            try:
                tmp_prefix = f"tmp-checkout--{self.name.replace('/','-')}-"
                with tempfile.TemporaryDirectory(
                    dir=work_dir, prefix=tmp_prefix
                ) as tmpdir:
                    echo(f"Checking out source code for {self.name} in {tmpdir}")
                    self.checkout_status, checkout_dir = bst_checkout(self.name, tmpdir)
                    # returns the location of the checked out source if successful
                    # along with the appropriate checkout status
                    # checkout_dir will be "None" if there are no files checked out

                    if checkout_dir:
                        echo(f"Running license check software for {self.name}")
                        self.create_license_raw_output(checkout_dir)
                        shutil.copy(self.work_path, self.out_path)

            except PermissionError as pmn_error:
                echo(pmn_error)
                echo(
                    "Unable to create directory."
                    f" Insufficient permissions to create files in {work_dir}"
                )
                echo("Please check permissions, or try a different working directory.")
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
            echo(f"Running licensecheck failed for {self.work_path}")
            abort()
        os.rename(partfile_name, self.work_path)

    def get_dict(self):
        """Returns a dictionary with the key information about the dependency"""
        return {
            "dependency-name": self.name,
            "full-key": self.full_key,
            "checkout-status": self.checkout_status.value,
            "detected-licenses": sorted(list(self.license_outputs)),
            "output-filename": os.path.basename(self.out_path),
        }

    def update_license_list(self):
        """Reads the licensecheck output files, and updates the license_outputs
        attribute"""

        def stripline(line):
            line = line.rsplit("\t", 2)[1]
            line = line.replace("[generated file]", "")
            line = line.replace("GENERATED FILE", "")
            line = line.strip()
            return line

        if os.path.isfile(self.work_path):
            with open(self.work_path, mode="r") as openfile:
                self.license_outputs = {stripline(line) for line in openfile}

            self.license_outputs.difference_update(INVALID_LICENSE_VALUES)
