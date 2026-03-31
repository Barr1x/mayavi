pipeline {
    agent any

    environment {
        SONAR_HOST_URL    = 'http://sonarqube.devops.svc.cluster.local:9000'
        SONAR_PROJECT_KEY = 'mayavi'
    }

    stages {

        stage('SonarQube Analysis') {
            steps {
                script {
                    // Generate a fresh token using admin credentials (automated)
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

                    // Revoke the token after use
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

                    if (qgStatus == 'ERROR') {
                        echo "BLOCKER issues found — Hadoop job would NOT run."
                        currentBuild.result = 'UNSTABLE'
                    } else {
                        echo "No blocker issues — Hadoop job would run (not yet deployed)."
                    }

                    echo "SonarQube dashboard: ${SONAR_HOST_URL}/dashboard?id=${SONAR_PROJECT_KEY}"
                }
            }
        }
    }
}
