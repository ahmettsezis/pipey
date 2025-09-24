document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('schedule-form');
    const messageArea = document.getElementById('message-area');
    const jobsTableBody = document.querySelector('#jobs-table tbody');
    const projectSelect = document.getElementById('project-select');
    const pipelineSelect = document.getElementById('pipeline-select');
    const refreshAllBtn = document.getElementById('refresh-all');
    const datetimeInput = document.getElementById('run-datetime');
    const desktechInput = document.getElementById('desktech-id');

    // --- Function to set minimum datetime (current time + 2 minutes) ---
    function setMinDateTime() {
        const now = new Date();
        now.setMinutes(now.getMinutes() + 2); // Add 2 minutes to current time
        
        // Format datetime for datetime-local input (YYYY-MM-DDTHH:MM)
        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, '0');
        const day = String(now.getDate()).padStart(2, '0');
        const hours = String(now.getHours()).padStart(2, '0');
        const minutes = String(now.getMinutes()).padStart(2, '0');
        
        const minDateTime = `${year}-${month}-${day}T${hours}:${minutes}`;
        // Remove min attribute to prevent browser validation
        // datetimeInput.min = minDateTime;
        
        return minDateTime;
    }

    // --- Function to validate selected datetime ---
    function validateDateTime(selectedDateTime) {
        const now = new Date();
        const selected = new Date(selectedDateTime);
        const minAllowed = new Date(now.getTime() + 2 * 60 * 1000); // Current time + 2 minutes
        
        if (selected < minAllowed) {
            const minTime = minAllowed.toLocaleString('tr-TR', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
            
            showMessage(`⚠️ Lütfen şu andan en az 2 dakika sonrası bir zaman seçin. En erken: ${minTime}`, true);
            return false;
        }
        
        return true;
    }

    // --- Function to validate desktech ID (positive integer) ---
    function validateDesktechId(value) {
        if (!value) {
            showMessage('Lütfen Desktech ID alanını doldurun.', true);
            return false;
        }
        const re = /^[1-9]\d*$/;
        if (!re.test(String(value).trim())) {
            showMessage('Desktech ID pozitif sayısal bir değer olmalıdır.', true);
            return false;
        }
        return true;
    }

    // --- Function to fetch and populate projects dropdown ---
    async function fetchProjects() {
        try {
            const response = await fetch('/projects');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const projects = await response.json();
            updateProjectDropdown(projects);
        } catch (error) {
            console.error('Error fetching projects:', error);
            projectSelect.innerHTML = '<option value="">Error loading projects</option>';
        }
    }

    // --- Function to update project dropdown ---
    function updateProjectDropdown(projects) {
        projectSelect.innerHTML = '<option value="">Select a project...</option>';
        
        projects.forEach(project => {
            const option = document.createElement('option');
            option.value = project.name;
            option.textContent = project.name;
            projectSelect.appendChild(option);
        });
    }

    // --- Function to fetch and populate pipelines dropdown ---
    async function fetchPipelines(projectName) {
        if (!projectName) {
            pipelineSelect.innerHTML = '<option value="">First select a project...</option>';
            pipelineSelect.disabled = true;
            return;
        }

        try {
            const response = await fetch(`/pipelines?project=${encodeURIComponent(projectName)}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const pipelines = await response.json();
            updatePipelineDropdown(pipelines);
            pipelineSelect.disabled = false;
        } catch (error) {
            console.error('Error fetching pipelines:', error);
            pipelineSelect.innerHTML = '<option value="">Error loading pipelines</option>';
            pipelineSelect.disabled = true;
        }
    }

    // --- Function to update pipeline dropdown ---
    function updatePipelineDropdown(pipelines) {
        pipelineSelect.innerHTML = '<option value="">Select a pipeline...</option>';
        
        pipelines.forEach(pipeline => {
            const option = document.createElement('option');
            option.value = pipeline.id;
            option.textContent = `${pipeline.name} (${pipeline.path})`;
            pipelineSelect.appendChild(option);
        });
    }

    // --- Function to refresh all data ---
    async function refreshAll() {
        refreshAllBtn.textContent = '🔄 Refreshing...';
        refreshAllBtn.disabled = true;
        
        try {
            // Refresh projects first
            const projectsResponse = await fetch('/refresh-projects', { method: 'POST' });
            if (!projectsResponse.ok) {
                throw new Error('Failed to refresh projects');
            }
            
            // Fetch updated projects
            await fetchProjects();
            
            // If a project is selected, refresh its pipelines
            const selectedProject = projectSelect.value;
            if (selectedProject) {
                const pipelinesResponse = await fetch('/refresh-pipelines', { 
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ project: selectedProject })
                });
                if (pipelinesResponse.ok) {
                    await fetchPipelines(selectedProject);
                }
            }
            
            // Refresh jobs
            await fetchJobs();
            
            showMessage('All data refreshed successfully!');
        } catch (error) {
            console.error('Error refreshing data:', error);
            showMessage('Failed to refresh data', true);
        } finally {
            refreshAllBtn.textContent = '🔄 Refresh All';
            refreshAllBtn.disabled = false;
        }
    }

    // --- Function to fetch and display jobs ---
    async function fetchJobs() {
        try {
            const response = await fetch('/jobs');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const jobs = await response.json();
            updateJobsTable(jobs);
        } catch (error) {
            console.error('Error fetching jobs:', error);
        }
    }

    // --- Function to update jobs table ---
    function updateJobsTable(jobs) {
        jobsTableBody.innerHTML = '';
        
        if (jobs.length === 0) {
            const row = document.createElement('tr');
            row.innerHTML = `<td colspan="5">No jobs scheduled yet.</td>`;
            jobsTableBody.appendChild(row);
            return;
        }
        
        jobs.forEach(job => {
            const row = document.createElement('tr');
            
            // Add status class for styling
            let statusClass = '';
            if (job.status === 'Scheduled') statusClass = 'status-scheduled';
            else if (job.status === 'Triggered Successfully') statusClass = 'status-triggered';
            else if (job.status === 'Failed') statusClass = 'status-failed';
            else if (job.status === 'Cancelled') statusClass = 'status-failed';
            
            // Render ID cell as clickable link: prefer build link, else fall back to definition link
            const idCellHtml = (() => {
                if (job.build_url && job.build_url !== '#') {
                    return `<a href="${job.build_url}" target="_blank" rel="noopener" class="job-link">Build #${job.build_id || ''}</a>`;
                }
                if (job.definition_url) {
                    return `<a href="${job.definition_url}" target="_blank" rel="noopener" class="job-link">Pipeline #${job.definition_id}</a>`;
                }
                return `${job.id}`;
            })();

            // Create cancel button (enabled for Scheduled and Chained (Waiting) jobs)
            const canCancel = job.status === 'Scheduled' || (job.is_chained && job.status === 'Chained (Waiting)');
            const cancelBtnHtml = canCancel ?
                `<button class="cancel-btn" data-job-id="${job.id}">Cancel</button>` :
                `<button class="cancel-btn" disabled>Cancel</button>`;

            // Create chain button (only for Scheduled jobs), disable if chain_queue length >= 5
            let chainBtnHtml = '';
            if (job.status === 'Scheduled') {
                const chainCount = Array.isArray(job.chain_queue) ? job.chain_queue.length : 0;
                const chainDisabledAttr = chainCount >= 5 ? 'disabled' : '';
                chainBtnHtml = ` <button class="chain-btn" data-job-id="${job.id}" ${chainDisabledAttr}>+Chain</button>`;
            }
            const parentInfoHtml = job.is_chained && job.parent_job_id ? (() => {
                const p = jobs.find(j => j.id === job.parent_job_id);
                if (p) {
                    const parentLink = (p.build_url && p.build_url !== '#')
                        ? `<a href="${p.build_url}" target="_blank" rel="noopener" class="job-link">Build #${p.build_id || ''}</a>`
                        : (p.definition_url ? `<a href="${p.definition_url}" target="_blank" rel="noopener" class="job-link">Pipeline #${p.definition_id}</a>` : p.id);
                    return `<div class="parent-info">Parent: ${p.pipeline_name} (${parentLink})</div>`;
                }
                return `<div class="parent-info">Parent: ${job.parent_job_id}</div>`;
            })() : '';
            const pipelineCellHtml = `${job.pipeline_name}${parentInfoHtml}`;
            
            row.innerHTML = `
                <td>${idCellHtml}</td>
                <td>${pipelineCellHtml}</td>
                <td>${job.run_time}</td>
                <td class="${statusClass}">${job.status}</td>
                <td>${cancelBtnHtml}${chainBtnHtml}</td>
            `;
            
            jobsTableBody.appendChild(row);
        });
        
        // Add event listeners to cancel buttons
        document.querySelectorAll('.cancel-btn:not([disabled])').forEach(btn => {
            btn.addEventListener('click', function() {
                const jobId = this.getAttribute('data-job-id');
                cancelJob(jobId);
            });
        });

        // Add event listeners to chain buttons
        document.querySelectorAll('.chain-btn:not([disabled])').forEach(btn => {
            btn.addEventListener('click', async function() {
                const parentJobId = this.getAttribute('data-job-id');
                const definitionId = pipelineSelect.value;
                const desktechId = desktechInput ? desktechInput.value.trim() : '';

                if (!definitionId) {
                    showMessage('Lütfen üstte bir pipeline seçin (Chain eklenecek pipeline).', true);
                    return;
                }
                if (!desktechId || !validateDesktechId(desktechId)) {
                    if (desktechInput) desktechInput.focus();
                    return;
                }

                try {
                    const response = await fetch('/chain', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            parent_job_id: parentJobId,
                            definition_id: definitionId,
                            desktechID: String(desktechId)
                        })
                    });
                    const result = await response.json();
                    if (response.ok) {
                        showMessage(`Chain eklendi. Toplam chain: ${result.chain_count}`);
                        fetchJobs();
                    } else {
                        throw new Error(result.message || 'Chain eklenemedi');
                    }
                } catch (err) {
                    console.error('Error adding chain:', err);
                    showMessage(err.message, true);
                }
            });
        });
    }
    
    // --- Function to cancel a job ---
    async function cancelJob(jobId) {
        if (!confirm('Are you sure you want to cancel this job?')) {
            return;
        }
        
        try {
            const response = await fetch(`/cancel-job/${jobId}`, { method: 'POST' });
            const data = await response.json();
            
            if (response.ok) {
                showMessage('Job cancelled successfully.');
                await fetchJobs(); // Refresh the jobs list
            } else {
                throw new Error(data.message || 'Failed to cancel job.');
            }
        } catch (error) {
            console.error('Error cancelling job:', error);
            showMessage(`Failed to cancel job: ${error.message}`, true);
        }
    }

    // --- Function to display feedback messages ---
    function showMessage(message, isError = false) {
        if (!messageArea) {
            console.error('messageArea element not found!');
            return;
        }
        
        messageArea.textContent = message;
        messageArea.className = isError ? 'message-error' : 'message-success';
        
        setTimeout(() => {
            messageArea.className = '';
        }, 5000); // Hide after 5 seconds
    }

    // --- Event Listener for the form submission ---
    form.addEventListener('submit', async function(event) {
        event.preventDefault();

        const definitionId = pipelineSelect.value;
        const runDatetime = document.getElementById('run-datetime').value;
        const desktechId = desktechInput ? desktechInput.value.trim() : '';

        if (!definitionId || !runDatetime || !desktechId) {
            showMessage('Lütfen tüm alanları doldurun.', true);
            return;
        }

        // Validate datetime before submitting
        if (!validateDateTime(runDatetime)) {
            return; // Error message already shown in validateDateTime
        }

        // Validate desktech ID before submitting
        if (!validateDesktechId(desktechId)) {
            if (desktechInput) desktechInput.focus();
            return; // Error message already shown in validateDesktechId
        }

        try {
            const response = await fetch('/schedule', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    definition_id: definitionId,
                    run_datetime: runDatetime,
                    desktechID: String(desktechId)
                }),
            });

            const result = await response.json();

            if (response.ok) {
                showMessage(`Job ${result.job_id} scheduled successfully!`);
                form.reset();
                fetchJobs(); // Refresh the list immediately
            } else {
                throw new Error(result.message || 'Failed to schedule the job.');
            }
        } catch (error) {
            console.error('Error scheduling job:', error);
            showMessage(error.message, true);
        }
    });

    // --- Event listeners ---
    projectSelect.addEventListener('change', function() {
        const selectedProject = this.value;
        fetchPipelines(selectedProject);
    });
    
    // Add datetime validation on input change
    datetimeInput.addEventListener('change', function() {
        if (this.value) {
            validateDateTime(this.value);
        }
    });

    // Add datetime validation on input (real-time)
    datetimeInput.addEventListener('input', function() {
        if (this.value) {
            validateDateTime(this.value);
        }
    });
    
    refreshAllBtn.addEventListener('click', refreshAll);

    // --- Initial setup and periodic refresh ---
    setMinDateTime(); // Set initial min datetime
    fetchProjects(); // Fetch projects on page load
    fetchJobs(); // Fetch jobs on page load
    
    // Refresh jobs every 5 seconds
    setInterval(fetchJobs, 5000);
    
    // Update min datetime every minute to keep it current
    setInterval(setMinDateTime, 60000);
});