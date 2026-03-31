pipeline {
    agent any

    environment {
        SONAR_HOST_URL    = 'http://sonarqube.devops.svc.cluster.local:9000'
        SONAR_PROJECT_KEY = 'mayavi'
        GCP_PROJECT       = 'rising-apricot-491917-g5'
        DATAPROC_CLUSTER  = 'hadoop-cluster'
        DATAPROC_REGION   = 'us-central1'
        RESULTS_FILE      = '/var/jenkins_home/hadoop-results/line-counts.txt'
    }

    stages {

        stage('SonarQube Analysis') {
            steps {
                script {
                    def scannerHome = tool 'SonarScanner'
                    withSonarQubeEnv('SonarQube') {
                        sh """
                            ${scannerHome}/bin/sonar-scanner \
                                -Dsonar.projectKey=${SONAR_PROJECT_KEY} \
                                -Dsonar.sources=. \
                                -Dsonar.python.version=3 \
                                -Dsonar.host.url=${SONAR_HOST_URL}
                        """
                    }
                }
            }
        }

        stage('Quality Gate') {
            steps {
                script {
                    // Give SonarQube time to finish processing
                    sleep(time: 30, unit: 'SECONDS')

                    def qgStatus = sh(
                        script: """
                            curl -sf '${SONAR_HOST_URL}/api/qualitygates/project_status?projectKey=${SONAR_PROJECT_KEY}' \
                            | python3 -c "import sys,json; print(json.load(sys.stdin)['projectStatus']['status'])"
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

        stage('Run Hadoop MapReduce') {
            when { expression { env.QG_STATUS != 'ERROR' } }
            steps {
                sh '''
                    # Get GCP access token from GKE node metadata server
                    TOKEN=$(curl -sf \
                        -H "Metadata-Flavor: Google" \
                        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
                        | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

                    # Find the Dataproc staging bucket
                    BUCKET=$(curl -sf \
                        -H "Authorization: Bearer $TOKEN" \
                        "https://storage.googleapis.com/storage/v1/b?project=${GCP_PROJECT}&prefix=rising-apricot-491917-g5-dataproc-staging" \
                        | python3 -c "import sys,json; items=json.load(sys.stdin).get('items',[]); print(items[0]['name'] if items else '')")

                    if [ -z "$BUCKET" ]; then
                        echo "ERROR: Dataproc staging bucket not found. Deploy the Hadoop cluster first."
                        exit 1
                    fi
                    echo "Using bucket: $BUCKET"

                    # Prepare input: filename<TAB>line_content for every file in the repo
                    INPUT_FILE="/tmp/repo-lines-${BUILD_NUMBER}.txt"
                    find . -type f ! -path '*/.git/*' | while read f; do
                        rel="${f#./}"
                        while IFS= read -r line; do
                            printf '%s\t%s\n' "$rel" "$line"
                        done < "$f"
                    done > "$INPUT_FILE"
                    echo "Input lines: $(wc -l < $INPUT_FILE)"

                    # Upload input and scripts to GCS
                    INPUT_GCS="gs://$BUCKET/input/build-${BUILD_NUMBER}/repo-lines.txt"
                    MAPPER_GCS="gs://$BUCKET/scripts/mapper.py"
                    REDUCER_GCS="gs://$BUCKET/scripts/reducer.py"
                    OUTPUT_GCS="gs://$BUCKET/output/build-${BUILD_NUMBER}"

                    for FILE_URI in "$INPUT_GCS" "$MAPPER_GCS" "$REDUCER_GCS"; do
                        FOLDER=$(dirname "${FILE_URI#gs://*/}")
                        echo "Uploading to $FILE_URI"
                    done

                    # Upload via Storage JSON API
                    curl -sf -X POST \
                        -H "Authorization: Bearer $TOKEN" \
                        -H "Content-Type: text/plain" \
                        --data-binary @"$INPUT_FILE" \
                        "https://storage.googleapis.com/upload/storage/v1/b/$BUCKET/o?uploadType=media&name=input/build-${BUILD_NUMBER}/repo-lines.txt" > /dev/null

                    curl -sf -X POST \
                        -H "Authorization: Bearer $TOKEN" \
                        -H "Content-Type: text/plain" \
                        --data-binary @"$(dirname $0)/hadoop-job/mapper.py" \
                        "https://storage.googleapis.com/upload/storage/v1/b/$BUCKET/o?uploadType=media&name=scripts/mapper.py" > /dev/null 2>&1 || true

                    curl -sf -X POST \
                        -H "Authorization: Bearer $TOKEN" \
                        -H "Content-Type: text/plain" \
                        --data-binary @"$(dirname $0)/hadoop-job/reducer.py" \
                        "https://storage.googleapis.com/upload/storage/v1/b/$BUCKET/o?uploadType=media&name=scripts/reducer.py" > /dev/null 2>&1 || true

                    # Submit Hadoop streaming job via Dataproc REST API
                    JOB_RESPONSE=$(curl -sf -X POST \
                        -H "Authorization: Bearer $TOKEN" \
                        -H "Content-Type: application/json" \
                        "https://dataproc.googleapis.com/v1/projects/${GCP_PROJECT}/regions/${DATAPROC_REGION}/jobs:submit" \
                        -d "{
                            \"job\": {
                                \"placement\": { \"clusterName\": \"${DATAPROC_CLUSTER}\" },
                                \"hadoopJob\": {
                                    \"mainJarFileUri\": \"file:///usr/lib/hadoop/hadoop-streaming.jar\",
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
                        }")

                    JOB_ID=$(echo "$JOB_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['reference']['jobId'])")
                    echo "Submitted Dataproc job: $JOB_ID"

                    # Poll until job completes
                    while true; do
                        STATE=$(curl -sf \
                            -H "Authorization: Bearer $TOKEN" \
                            "https://dataproc.googleapis.com/v1/projects/${GCP_PROJECT}/regions/${DATAPROC_REGION}/jobs/$JOB_ID" \
                            | python3 -c "import sys,json; print(json.load(sys.stdin)['status']['state'])")
                        echo "Job state: $STATE"
                        if [ "$STATE" = "DONE" ]; then break; fi
                        if [ "$STATE" = "ERROR" ] || [ "$STATE" = "CANCELLED" ]; then
                            echo "Hadoop job failed with state: $STATE"
                            exit 1
                        fi
                        sleep 20
                    done

                    env.OUTPUT_GCS = "$OUTPUT_GCS"
                    env.TOKEN = "$TOKEN"
                    env.BUCKET = "$BUCKET"
                '''
            }
        }

        stage('Display Results') {
            when { expression { env.QG_STATUS != 'ERROR' } }
            steps {
                sh '''
                    echo "============================================================"
                    echo "  Hadoop MapReduce Results — Line counts per file"
                    echo "============================================================"

                    # Fetch output from GCS
                    TOKEN=$(curl -sf \
                        -H "Metadata-Flavor: Google" \
                        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
                        | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

                    OUTPUT_GCS="gs://$(curl -sf \
                        -H "Authorization: Bearer $TOKEN" \
                        "https://storage.googleapis.com/storage/v1/b?project=${GCP_PROJECT}&prefix=rising-apricot-491917-g5-dataproc-staging" \
                        | python3 -c "import sys,json; items=json.load(sys.stdin).get('items',[]); print(items[0]['name'] if items else '')")/output/build-${BUILD_NUMBER}"

                    BUCKET=$(echo "$OUTPUT_GCS" | cut -d/ -f3)

                    # List and download result parts
                    curl -sf \
                        -H "Authorization: Bearer $TOKEN" \
                        "https://storage.googleapis.com/storage/v1/b/$BUCKET/o?prefix=output/build-${BUILD_NUMBER}/part-" \
                        | python3 -c "
import sys, json
items = json.load(sys.stdin).get('items', [])
for item in items:
    print(item['name'])
" | while read PART; do
                        curl -sf \
                            -H "Authorization: Bearer $TOKEN" \
                            "https://storage.googleapis.com/storage/v1/b/$BUCKET/o/$(python3 -c \"import urllib.parse; print(urllib.parse.quote('$PART', safe=''))\") ?alt=media"
                    done | tee "${RESULTS_FILE}"

                    echo "============================================================"
                    echo "Results saved to: ${RESULTS_FILE}"
                    echo "SonarQube dashboard: ${SONAR_HOST_URL}/dashboard?id=${SONAR_PROJECT_KEY}"
                    echo "============================================================"
                '''
            }
        }
    }

    post {
        always {
            echo "Pipeline finished. Quality Gate: ${env.QG_STATUS ?: 'N/A'}"
            echo "SonarQube: ${SONAR_HOST_URL}/dashboard?id=${SONAR_PROJECT_KEY}"
        }
    }
}
