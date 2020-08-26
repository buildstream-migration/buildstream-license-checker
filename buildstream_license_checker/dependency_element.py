"""Contains the DependencyElement class, as used by the bst_license_checker script.
A DependencyElement object stores information about exactly one buildstream element,
and has the methods to extract and return license information for that one element."""

import os.path
import sys
import subprocess
import tempfile
import shutil
from enum import Enum

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


def abort():
    """Print short message and exit"""
    print("Aborting buildstream-license-checker", file=sys.stderr)
    sys.exit(1)


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
                    print(
                        f"Checking out source code for {self.name} in {tmpdir}",
                        file=sys.stderr,
                    )
                    self.checkout_source(tmpdir)
                    # sets checkout_status if successful

                    if self.checkout_status == CheckoutStatus.checkout_succeeded:
                        print(
                            f"Running license check software for {self.name}",
                            file=sys.stderr,
                        )
                        self.create_license_raw_output(tmpdir)
                        shutil.copy(self.work_path, self.out_path)

            except PermissionError as pmn_error:
                print(pmn_error, file=sys.stderr)
                print(
                    "Unable to create directory. Insufficient permissions to"
                    f" create files in {work_dir}\nPlease check permissions,"
                    " or try a different working directory.",
                    file=sys.stderr,
                )
                abort()

    def checkout_source(self, checkout_path):
        """Checks out the source-code of a specified element, into a specified
        directory"""
        return_code = subprocess.call(
            ["bst", "--colors", "workspace", "open", self.name, checkout_path]
        )
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
            print(f"Running licensecheck failed for {self.work_path}", file=sys.stderr)
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
            line = line.strip()
            return line

        if os.path.isfile(self.work_path):
            with open(self.work_path, mode="r") as openfile:
                self.license_outputs = {stripline(line) for line in openfile}

            self.license_outputs.difference_update(INVALID_LICENSE_VALUES)
