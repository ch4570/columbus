pub struct Job {
    pub size: usize,
}

pub fn queued_job() -> Job {
    Job { size: 1 }
}
