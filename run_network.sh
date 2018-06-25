#!/bin/bash

in_group=( `cat ~/local_group.txt`)
parent=(`hostname`)
k=1
for i in "${in_group[@]}"
do
    printf "_________ %s __________ %d of %d\n" "$i" "$k" "${#in_group[@]}"
    ((k++))
    ssh $i "cd ~/glance && ./run_glance.sh"
done

