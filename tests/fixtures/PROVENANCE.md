# Test fixture provenance

No images of real people are committed to this repository (docs/12 §5).

`tools/fetch_test_fixtures.py` downloads the following files into `tests/fixtures/local/`
(gitignored) for integration tests and local demos:

| File | Content | Source | Licence |
|---|---|---|---|
| obama.jpg, obama2.jpg | Official portrait / address photo | White House photographs, via the `face_recognition` project examples | Public domain (U.S. federal government work) |
| biden.jpg | Official photograph | White House photograph, same source | Public domain |
| two_people.jpg | Two people, used for the MULTIPLE_FACES rule | White House photograph, same source | Public domain |

These are used only to test the pipeline mechanics (detection, multi-face blocking, same vs.
different identity). They are **not** a validation set and support no accuracy or fairness claim
(docs/13). Synthetic images (blank frames) are generated in the tests themselves.
