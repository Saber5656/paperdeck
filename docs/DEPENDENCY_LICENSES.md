# Dependency license decisions

Runtime dependencies are checked by `scripts/check_licenses.py`. Unknown licenses
fail the build. A disjunction permits choosing a compatible license; every term of
a conjunction must pass. Nested SPDX expressions require explicit review.

## Existing TLS trust data: certifi

The HTTPX dependency includes certifi's Mozilla CA trust data. The license gate
therefore has one package-specific exception for certifi's existing MPL-2.0 license.
This exception does not cover a license change or other MPL packages. It preserves
the existing verified HTTPS path and does not change paperdeck's MIT license.

Certifi is installed as an unmodified separate dependency, not copied into the
paperdeck source tree or generated reader. Preserve its upstream license notices.
Its source and license are available in the
[certifi repository](https://github.com/certifi/python-certifi). Mozilla describes
MPL's file-level scope and distribution requirements in its
[official FAQ, questions 7–11](https://www.mozilla.org/en-US/MPL/2.0/FAQ/).

This corrects the original blanket permissive-only gate, which was inconsistent
with the already selected HTTPX dependency. New exceptions require a recorded
package-specific reason and tests that reject unrelated packages and license changes.

## PDFium binary notices

The pypdfium2 5.13.0 wheel reports `BSD-3-Clause, Apache-2.0, dependency licenses`.
Its shipped notices were inspected: PDFium/BSD, Abseil and LLVM/Apache (LLVM
exception), MIT utilities, FreeType/FTL, ICU/Unicode, JPEG/IJG, OpenJPEG/BSD,
PNG/libpng, TIFF and zlib. ICU's Autoconf helper notice explicitly includes an
exception for the generated configuration script; this is not a GPL-only runtime.
The gate recognizes this exact version and metadata combination. A new version
must have its bundled notices reviewed before updating this entry. Notices remain
in the separately installed dependency wheel; paperdeck does not relabel them.

## Bundled reader assets

KaTeX 0.18.7 is MIT-licensed. Its license and exact file checksums ship with the
wheel and source distribution. Generated HTML uses the bundled assets without
contacting a CDN. The browser's system text fonts are not redistributed.
