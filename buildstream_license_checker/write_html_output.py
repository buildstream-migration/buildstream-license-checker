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
Write HTML output
=================

Outputs a human readable html file listing the license scan results.
"""

from buildstream_license_checker.utils import CheckoutStatus


def write_html_output(results_dict, html_output_path):
    """Outputs a human readable html file listing the license scan results."""
    html_dependencies = ""

    # get html for dependencies
    for dep in results_dict["dependency-list"]:
        # basic info for each dependency
        dep_start = DEP_HTML_START.format(
            dependency_name=dep["dependency-name"],
            dependency_checkout_status=dep["checkout-status"],
            full_key_1=dep["full-key"][:32],
            full_key_2=dep["full-key"][32:],
        )

        # licensecheck results
        dep_middle = ""
        if dep["checkout-status"] == CheckoutStatus.checkout_succeeded.value:
            dep_middle += LICENSE_HTML_START.format(
                output_basename=dep["output-filename"]
            )
            for license_line in dep["detected-licenses"]:
                dep_middle += LICENSE_HTML_LINE.format(license_line=license_line)
            dep_middle += LICENSE_HTML_END
        elif dep["checkout-status"] == CheckoutStatus.checkout_failed.value:
            dep_middle += CHECKOUT_FAILED_HTML
        elif dep["checkout-status"] == CheckoutStatus.fetch_failed.value:
            dep_middle += FETCH_FAILED_HTML
        elif dep["checkout-status"] == CheckoutStatus.no_sources.value:
            dep_middle += NO_SOURCES_HTML

        # pull all the info together (for each dependency)
        html_dependencies += dep_start
        html_dependencies += dep_middle
        html_dependencies += DEP_HTML_END

    # write html to output file
    with open(html_output_path, mode="w") as outfile:
        outfile.write(HTML_START)
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
<div style="max-width: 50em; font-size: small; text-align: justify;">
<p>The script was unable to check out any sources for this element. If this is a
BuildStream 1 project, and the element does not have any sources (eg a stack element, or
a filter element) then this is the expected result.  Otherwise, this result may mean
there has been an error.</p>
<p> Consider using the --ignorelist option and adding this element to the ignore list,
to speed up future scans.</p>
</div> """

FETCH_FAILED_HTML = """
<strong>NO RESULTS:</strong> 'bst fetch' command failed.
<div style="max-width: 50em; font-size: small; text-align: justify;">
<p>BuildStream's fetch command was unable to fetch sources for this element. This could
mean that there is an error in the element (such a mistake in the source URL), or it
could mean that an external resource is not currently available for download.</p>
</div> """

NO_SOURCES_HTML = """
<strong>NO RESULTS:</strong> Element has no sources to scan.
<div style="max-width: 50em; font-size: small; text-align: justify;">
<p> BuildStream's "source checkout" command completed succesfully, but the checkout
folder was empty. This generally means that the element had no sources to check out.
(eg a stack element, or a filter element).  </p>
<p> Consider using the --ignorelist option and adding this element to the ignore list,
to speed up future scans.</p>
</div> """
