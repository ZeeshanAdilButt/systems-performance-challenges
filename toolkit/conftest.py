"""Keep Hypothesis's files in .cache/ with the other tool caches, instead of a .hypothesis
folder at the top of the repository."""

from hypothesis.configuration import set_hypothesis_home_dir

set_hypothesis_home_dir(".cache/hypothesis")
