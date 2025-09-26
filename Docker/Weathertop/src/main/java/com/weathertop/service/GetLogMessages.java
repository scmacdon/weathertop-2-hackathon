package com.weathertop.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import software.amazon.awssdk.core.ResponseBytes;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Request;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Response;
import software.amazon.awssdk.services.s3.model.S3Object;

import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Comparator;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GetLogMessages {

    private static final Region REGION = Region.US_EAST_1;
    private static final String BUCKET_NAME = "weathertop2";
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH-mm");

    public String getHistoricalSummary(String language) {
        S3Client s3 = S3Client.builder()
                .region(REGION)
                .build();

        String latestFileKey = getLatestFileKey(s3, BUCKET_NAME, language);
        System.out.println("Latest file: " + latestFileKey);

        GetObjectRequest getRequest = GetObjectRequest.builder()
                .bucket(BUCKET_NAME)
                .key(latestFileKey)
                .build();

        ResponseBytes<GetObjectResponse> objectBytes = s3.getObjectAsBytes(getRequest);
        String jsonString = objectBytes.asString(StandardCharsets.UTF_8);

        try {
            JsonNode root = MAPPER.readTree(jsonString);
            JsonNode testsNode = root.path("results").path("tests");

            if (!testsNode.isArray()) {
                return "[]";
            }

            return MAPPER.writerWithDefaultPrettyPrinter().writeValueAsString(testsNode);
        } catch (Exception e) {
            throw new RuntimeException("Failed to parse JSON or extract tests node", e);
        }
    }

    public static String getLatestFileKey(S3Client s3Client, String bucketName, String languagePrefix) {
        Pattern filePattern = Pattern.compile(languagePrefix + "-(\\d{4}-\\d{2}-\\d{2}T\\d{2}-\\d{2})\\.json");

        ListObjectsV2Request request = ListObjectsV2Request.builder()
                .bucket(bucketName)
                .prefix(languagePrefix + "-")
                .build();

        ListObjectsV2Response response = s3Client.listObjectsV2(request);
        List<S3Object> objects = response.contents();

        return objects.stream()
                .map(S3Object::key)
                .filter(key -> filePattern.matcher(key).matches())
                .sorted(Comparator.comparing((String key) -> extractTimestamp(key, filePattern)).reversed())
                .findFirst()
                .orElseThrow(() -> new RuntimeException("No matching files found for prefix: " + languagePrefix));
    }

    private static LocalDateTime extractTimestamp(String key, Pattern pattern) {
        Matcher matcher = pattern.matcher(key);
        if (matcher.find()) {
            return LocalDateTime.parse(matcher.group(1), FORMATTER);
        } else {
            throw new RuntimeException("Invalid file format: " + key);
        }
    }
}
