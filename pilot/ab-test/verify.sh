# count tests failing when the agent's tests run on the snapshot code (non-test files reverted), vs the snapshot itself
run=$1; d=/srv/blind4/$run; cd $d || exit 1
root=$(git rev-list --max-parents=0 HEAD)
cmd=$(python3 -c "import json;print(json.load(open('.blind.json'))['test_cmd'])")
tdir=$(echo "$cmd" | awk '{print $NF}')
extra=$(echo "$cmd" | grep -o -- '--ignore=[^ ]*')
git checkout -q $root -- $(git diff --name-only $root HEAD | grep -v "^$tdir/" | grep -v '^\.blind' | while read f; do git cat-file -e $root:$f 2>/dev/null && echo $f; done)
# files the agent added outside tests (new modules) would linger; remove from index view by moving aside
added=$(git diff --name-only --diff-filter=A $root HEAD | grep -v "^$tdir/")
for f in $added; do mv $f $f.aside; done
eval "$cmd --tb=no -q --junitxml=./verify/j.xml" >/dev/null 2>&1; python3 ./junitfails.py ./verify/j.xml | sort > ./verify/$run.txt
for f in $added; do mv $f.aside $f; done
git checkout -q HEAD -- .
git status --porcelain | grep -v blind.json
echo "$run: $(wc -l < ./verify/$run.txt) failing on snapshot code"
