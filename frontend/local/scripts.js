document.addEventListener('DOMContentLoaded', () => {
    const modelSelect = document.getElementById('model');
    const kbList = document.getElementById('kb-list');
    const refreshKbBtn = document.getElementById('refresh-kb');
    const deepResearchCheckbox = document.getElementById('deep-research');
    const deepResearchParams = document.getElementById('deep-research-params');
    const researchForm = document.getElementById('research-form');
    const resultsContainer = document.getElementById('results');
    const uploadForm = document.getElementById('upload-form');
    const fileInput = document.getElementById('file-upload');
    const uploadStatus = document.getElementById('upload-status');
    const kbInput = document.getElementById('knowledge-base');

    function fetchKnowledgeBases() {
        fetch('/knowledge-bases')
            .then(response => response.json())
            .then(data => {
                kbList.innerHTML = '';
                if (data.knowledge_bases) {
                    data.knowledge_bases.forEach(kb => {
                        const option = document.createElement('option');
                        option.value = kb;
                        kbList.appendChild(option);
                    });
                }
            })
            .catch(error => console.error('Error fetching knowledge bases:', error));
    }

    // Fetch models and populate dropdown
    fetch('/models')
        .then(response => response.json())
        .then(data => {
            if (data.models) {
                modelSelect.innerHTML = '<option value="">Select a model</option>';
                data.models.forEach(model => {
                    const option = document.createElement('option');
                    option.value = model.id;
                    option.textContent = model.id;
                    modelSelect.appendChild(option);
                });
            } else {
                modelSelect.innerHTML = '<option value="">Could not load models</option>';
            }
        })
        .catch(error => {
            console.error('Error fetching models:', error);
            modelSelect.innerHTML = '<option value="">Error loading models</option>';
        });

    fetchKnowledgeBases();
    refreshKbBtn.addEventListener('click', fetchKnowledgeBases);

    // Toggle deep research params
    deepResearchCheckbox.addEventListener('change', () => {
        if (deepResearchCheckbox.checked) {
            deepResearchParams.classList.remove('hidden');
        } else {
            deepResearchParams.classList.add('hidden');
        }
    });

    // Handle form submission
    uploadForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const file = fileInput.files[0];
        const knowledgeBase = kbInput.value;

        if (!file || !knowledgeBase) {
            uploadStatus.textContent = 'Please select a file and a knowledge base.';
            return;
        }

        uploadStatus.textContent = `Uploading ${file.name}...`;

        const formData = new FormData();
        formData.append('file', file);
        formData.append('knowledge_base', knowledgeBase);

        fetch('/upload/', {
            method: 'POST',
            body: formData,
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            uploadStatus.textContent = `File uploaded successfully: ${data.filename}`;
        })
        .catch(error => {
            console.error('Error uploading file:', error);
            uploadStatus.textContent = `File upload failed: ${error.message}`;
        });
    });

    researchForm.addEventListener('submit', (event) => {
        event.preventDefault();
        resultsContainer.textContent = 'Research in progress...';

        const formData = new FormData(researchForm);
        const task = formData.get('task');
        const model = formData.get('model');
        const knowledgeBase = formData.get('knowledge-base');
        const deepResearch = document.getElementById('deep-research').checked;
        const maxIterations = formData.get('max-iterations');
        const maxSearchResults = formData.get('max-search-results');
        const maxContentResults = formData.get('max-content-results');

        const requestBody = {
            task: task,
            report_type: deepResearch ? 'deep_research' : 'research_report',
            report_source: 'local',
            tone: 'Objective',
            headers: null,
            repo_name: '',
            branch_name: '',
            fast_llm: `openai:${model}`,
            smart_llm: `openai:${model}`,
            knowledge_base: knowledgeBase,
            deep_research_config: deepResearch ? {
                max_iterations: parseInt(maxIterations, 10),
                max_search_results_per_query: parseInt(maxSearchResults, 10),
                max_content_results_per_query: parseInt(maxContentResults, 10)
            } : null,
            generate_in_background: false
        };

        fetch('/report/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody),
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            resultsContainer.textContent = data.report;
        })
        .catch(error => {
            console.error('Error starting research:', error);
            resultsContainer.textContent = `An error occurred: ${error.message}`;
        });
    });
});
