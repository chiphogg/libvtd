# libvtd

Python library for a GTD Trusted System.

Supports both python 2 and 3, so it should work no matter which version of vim you're using.

## Running tests

Run the following command:

```sh
(for V in 2 3; do python$V -m unittest discover || exit $V; done) || echo "python$? failed!"
```

Either all the tests will pass, or the last line of the output will tell you which version failed.
