plugins {
    `java-library`
}

dependencies {
    api("org.springframework.boot:spring-boot-starter-web")
    api("com.fasterxml.jackson.dataformat:jackson-dataformat-yaml")
    api("dev.langchain4j:langchain4j:0.36.2")
    api("dev.langchain4j:langchain4j-open-ai:0.36.2")
    implementation("org.slf4j:slf4j-api")
}
