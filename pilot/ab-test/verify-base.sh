# failures of the untouched snapshot (pre-existing), per repo, using the r1 workspace at its root commit
repo=$1; d=/srv/blind4/$repo-r1; cd $d; root=$(git rev-list --max-parents=0 HEAD)
cmd=$(python3 -c "import json;print(json.load(open('.blind.json'))['test_cmd'])")
added=$(git diff --name-only --diff-filter=A $root HEAD)
for f in $added; do mv $f $f.aside; done
git checkout -q $root -- $(git diff --name-only --diff-filter=M $root HEAD)
eval "$cmd --tb=no -q --junitxml=./verify/j.xml" >/dev/null 2>&1; python3 ./junitfails.py ./verify/j.xml | sort > ./verify/base-$repo.txt
for f in $added; do mv $f.aside $f; done
git checkout -q HEAD -- .
echo "$repo snapshot failures: $(wc -l < ./verify/base-$repo.txt)"
