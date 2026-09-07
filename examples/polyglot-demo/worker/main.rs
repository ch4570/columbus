mod queue;

fn validate_job(size: usize) -> bool {
    size > 0
}

fn process_job(size: usize) -> bool {
    validate_job(size)
}
