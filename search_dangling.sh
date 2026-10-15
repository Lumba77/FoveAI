#!/bin/bash
git fsck --lost-found > /dev/null 2>&1
echo "Searching dangling blobs..."
for blob in $(ls .git/lost-found/other/ 2>/dev/null); do
  content=$(git cat-file -p $blob 2>/dev/null | grep -iaE "theme gallery|theme engine|theme manufactor")
  if [ ! -z "$content" ]; then
    echo "Found in blob $blob"
  fi
done

echo "Searching dangling commits..."
for commit in $(ls .git/lost-found/commit/ 2>/dev/null); do
  git show $commit 2>/dev/null | grep -iaE "theme gallery|theme engine|theme manufactor" > /dev/null
  if [ $? -eq 0 ]; then
    echo "Found in commit $commit"
  fi
done
