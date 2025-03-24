# Useful UGE commands for submitting and maintaining tasks

## Add jobs to UGE:

`qsub <job.sh>`

### Add job with stdout and stderr:

`qsub -o <path>`: Specifies the output file for standard output.

`qsub -e <path>`: Specifies the output file for standard error.

### Adding them together:

`qsub -o out.log -e err.log <job.sh>`

## Check status of job:

`qstat -u $USER`

## Remove job from queue:

`qdel <jobID>`