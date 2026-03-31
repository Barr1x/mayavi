pipeline {
    agent any

    environment {
        SONAR_HOST_URL    = 'http://sonarqube.devops.svc.cluster.local:9000'
        SONAR_PROJECT_KEY = 'mayavi'
        GCP_PROJECT       = 'rising-apricot-491917-g5'
        DATAPROC_CLUSTER  = 'hadoop-cluster'
        DATAPROC_REGION   = 'us-central1'
        RESULTS_DIR       = '/var/jenkins_home/hadoop-results'
    }

    stages {

        stage('SonarQube Analysis') {
            steps {
                script {
                    def sonarToken = sh(
                        script: """
                            curl -sf -u admin:admin -X POST \
                              '${SONAR_HOST_URL}/api/user_tokens/generate?name=jenkins-${BUILD_NUMBER}&login=admin' \
                            | sed 's/.*"token":"\\([^"]*\\)".*/\\1/'
                        """,
                        returnStdout: true
                    ).trim()

                    def scannerHome = tool 'SonarScanner'
                    withSonarQubeEnv('SonarQube') {
                        sh """
                            ${scannerHome}/bin/sonar-scanner \
                                -Dsonar.projectKey=${SONAR_PROJECT_KEY} \
                                -Dsonar.sources=. \
                                -Dsonar.python.version=3 \
                                -Dsonar.host.url=${SONAR_HOST_URL} \
                                -Dsonar.login=${sonarToken}
                        """
                    }

                    sh """
                        curl -sf -u admin:admin -X POST \
                          '${SONAR_HOST_URL}/api/user_tokens/revoke?name=jenkins-${BUILD_NUMBER}&login=admin' || true
                    """
                }
            }
        }

        stage('Quality Gate') {
            steps {
                script {
                    sleep(time: 30, unit: 'SECONDS')

                    def qgStatus = sh(
                        script: """
                            curl -sf '${SONAR_HOST_URL}/api/qualitygates/project_status?projectKey=${SONAR_PROJECT_KEY}' \
                            | sed 's/.*"status":"\\([^"]*\\)".*/\\1/'
                        """,
                        returnStdout: true
                    ).trim()

                    echo "SonarQube Quality Gate: ${qgStatus}"
                    env.QG_STATUS = qgStatus

                    if (qgStatus == 'ERROR') {
                        echo "BLOCKER issues found — Hadoop job will NOT run."
                        currentBuild.result = 'UNSTABLE'
                    } else {
                        echo "No blocker issues — proceeding to Hadoop MapReduce."
                    }
                }
            }
        }

        stage('Prepare & Upload Input') {
            when { expression { env.QG_STATUS != 'ERROR' } }
            steps {
                sh '''
                    # Get GCS staging bucket name
                    TOKEN=$(curl -sf -H "Metadata-Flavor: Google" \
                        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
                        | sed 's/.*"access_token":"\\([^"]*\\)".*/\\1/')

                    BUCKET=$(curl -sf \
                        -H "Authorization: Bearer $TOKEN" \
                        "https://storage.googleapis.com/storage/v1/b?project=${GCP_PROJECT}&prefix=rising-apricot-491917-g5-dataproc-staging" \
                        | sed 's/.*"name":"\\([^"]*\\)".*/\\1/' | head -1)

                    echo "BUCKET=$BUCKET" > /tmp/hadoop-env-${BUILD_NUMBER}.sh

                    # Prepare input: filename<TAB>line for every file in the workspace
                    INPUT="/tmp/repo-lines-${BUILD_NUMBER}.txt"
                    find . -type f ! -path '*/.git/*' ! -path '*/.scannerwork/*' | sort | while read f; do
                        rel="${f#./}"
                        while IFS= read -r line || [ -n "$line" ]; do
                            printf '%s\t%s\n' "$rel" "$line"
                        done < "$f"
                    done > "$INPUT"
                    echo "Total input lines: $(wc -l < $INPUT)"

                    # Upload input
                    curl -sf -X POST \
                        -H "Authorization: Bearer $TOKEN" \
                        -H "Content-Type: text/plain" \
                        --data-binary @"$INPUT" \
                        "https://storage.googleapis.com/upload/storage/v1/b/$BUCKET/o?uploadType=media&name=input/build-${BUILD_NUMBER}/repo-lines.txt" > /dev/null

                    # Upload mapper and reducer from repo
                    curl -sf -X POST \
                        -H "Authorization: Bearer $TOKEN" \
                        -H "Content-Type: text/plain" \
                        --data-binary @"hadoop-job/mapper.py" \
                        "https://storage.googleapis.com/upload/storage/v1/b/$BUCKET/o?uploadType=media&name=scripts/mapper.py" > /dev/null

                    curl -sf -X POST \
                        -H "Authorization: Bearer $TOKEN" \
                        -H "Content-Type: text/plain" \
                        --data-binary @"hadoop-job/reducer.py" \
                        "https://storage.googleapis.com/upload/storage/v1/b/$BUCKET/o?uploadType=media&name=scripts/reducer.py" > /dev/null

                    echo "Upload complete"
                '''
            }
        }

        stage('Run Hadoop MapReduce') {
            when { expression { env.QG_STATUS != 'ERROR' } }
            steps {
                sh '''
                    TOKEN=$(curl -sf -H "Metadata-Flavor: Google" \
                        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
                        | sed 's/.*"access_token":"\\([^"]*\\)".*/\\1/')

                    BUCKET=$(curl -sf \
                        -H "Authorization: Bearer $TOKEN" \
                        "https://storage.googleapis.com/storage/v1/b?project=${GCP_PROJECT}&prefix=rising-apricot-491917-g5-dataproc-staging" \
                        | sed 's/.*"name":"\\([^"]*\\)".*/\\1/' | head -1)

                    INPUT_GCS="gs://$BUCKET/input/build-${BUILD_NUMBER}/repo-lines.txt"
                    OUTPUT_GCS="gs://$BUCKET/output/build-${BUILD_NUMBER}"

                    # Submit Dataproc streaming job
                    JOB_ID=$(curl -sf -X POST \
                        -H "Authorization: Bearer $TOKEN" \
                        -H "Content-Type: application/json" \
                        "https://dataproc.googleapis.com/v1/projects/${GCP_PROJECT}/regions/${DATAPROC_REGION}/jobs:submit" \
                        -d "{
                            \"job\": {
                                \"placement\": { \"clusterName\": \"${DATAPROC_CLUSTER}\" },
                                \"hadoopJob\": {
                                    \"mainJarFileUri\": \"file:///usr/lib/hadoop-mapreduce/hadoop-streaming.jar\",
                                    \"args\": [
                                        \"-mapper\",  \"python3 mapper.py\",
                                        \"-reducer\", \"python3 reducer.py\",
                                        \"-input\",   \"$INPUT_GCS\",
                                        \"-output\",  \"$OUTPUT_GCS\",
                                        \"-file\",    \"gs://$BUCKET/scripts/mapper.py\",
                                        \"-file\",    \"gs://$BUCKET/scripts/reducer.py\"
                                    ]
                                }
                            }
                        }" | sed 's/.*"jobId":"\\([^"]*\\)".*/\\1/')

                    echo "Submitted Dataproc job: $JOB_ID"
                    echo "JOB_ID=$JOB_ID" >> /tmp/hadoop-env-${BUILD_NUMBER}.sh
                    echo "BUCKET=$BUCKET" >> /tmp/hadoop-env-${BUILD_NUMBER}.sh

                    # Poll until done
                    while true; do
                        STATE=$(curl -sf \
                            -H "Authorization: Bearer $TOKEN" \
                            "https://dataproc.googleapis.com/v1/projects/${GCP_PROJECT}/regions/${DATAPROC_REGION}/jobs/$JOB_ID" \
                            | sed 's/.*"state":"\\([^"]*\\)".*/\\1/' | head -1)
                        echo "Job state: $STATE"
                        case "$STATE" in
                            DONE) echo "Job completed successfully"; break ;;
                            ERROR|CANCELLED) echo "Job failed: $STATE"; exit 1 ;;
                        esac
                        sleep 20
                    done
                '''
            }
        }

        stage('Display Results') {
            when { expression { env.QG_STATUS != 'ERROR' } }
            steps {
                sh '''
                    TOKEN=$(curl -sf -H "Metadata-Flavor: Google" \
                        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
                        | sed 's/.*"access_token":"\\([^"]*\\)".*/\\1/')

                    BUCKET=$(curl -sf \
                        -H "Authorization: Bearer $TOKEN" \
                        "https://storage.googleapis.com/storage/v1/b?project=${GCP_PROJECT}&prefix=rising-apricot-491917-g5-dataproc-staging" \
                        | sed 's/.*"name":"\\([^"]*\\)".*/\\1/' | head -1)

                    mkdir -p "${RESULTS_DIR}"
                    RESULTS_FILE="${RESULTS_DIR}/build-${BUILD_NUMBER}.txt"

                    echo "============================================================" | tee "$RESULTS_FILE"
                    echo "  Hadoop MapReduce Results — Line counts per file"           | tee -a "$RESULTS_FILE"
                    echo "  Build: ${BUILD_NUMBER} | Commit: ${GIT_COMMIT}"           | tee -a "$RESULTS_FILE"
                    echo "============================================================" | tee -a "$RESULTS_FILE"

                    # List output parts and download each
                    curl -sf \
                        -H "Authorization: Bearer $TOKEN" \
                        "https://storage.googleapis.com/storage/v1/b/$BUCKET/o?prefix=output/build-${BUILD_NUMBER}/part-" \
                    | grep -o '"name":"[^"]*"' | sed 's/"name":"//;s/"//' \
                    | while read PART; do
                        ENCODED=$(echo "$PART" | sed 's|/|%2F|g')
                        curl -sf \
                            -H "Authorization: Bearer $TOKEN" \
                            "https://storage.googleapis.com/storage/v1/b/$BUCKET/o/${ENCODED}?alt=media"
                    done | tee -a "$RESULTS_FILE"

                    echo "============================================================" | tee -a "$RESULTS_FILE"
                    echo "Results saved to: $RESULTS_FILE"
                    echo "SonarQube: ${SONAR_HOST_URL}/dashboard?id=${SONAR_PROJECT_KEY}"
                '''
            }
        }
    }

    post {
        always {
            script {
                def status = env.QG_STATUS ?: 'N/A'
                echo "Pipeline complete. Quality Gate: ${status}"
                if (status == 'ERROR') {
                    echo "Hadoop job was SKIPPED due to blocker issues."
                }
            }
        }
    }
}
