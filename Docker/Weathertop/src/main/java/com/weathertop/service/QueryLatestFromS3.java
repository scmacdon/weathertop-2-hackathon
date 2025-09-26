// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.weathertop.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import software.amazon.awssdk.core.ResponseBytes;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.*;

import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Comparator;
import java.util.List;
import java.util.regex.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

/*
  This code example is test code to query latest JSON files
  used for weathertop 2
 */
public class QueryLatestFromS3 {

    private static final Pattern FILE_PATTERN = Pattern.compile("java-(\\d{4}-\\d{2}-\\d{2}T\\d{2}-\\d{2})\\.json");
    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH-mm");


    public String readJsonFromS3(String language) {
        String bucketName = "weathertop2";
        Region region = Region.US_EAST_1;
        S3Client s3 = S3Client.builder()
                .region(region)
                .build();

        String latestFileKey = getLatestFileKey(s3, bucketName, language);
        System.out.println("📄 Latest file: " + latestFileKey);

        // Extract just the filename without .json
        String runId = latestFileKey.replace(".json", "");

        GetObjectRequest getRequest = GetObjectRequest.builder()
                .bucket(bucketName)
                .key(latestFileKey)
                .build();

        ResponseBytes<GetObjectResponse> objectBytes = s3.getObjectAsBytes(getRequest);
        String originalJson = objectBytes.asString(StandardCharsets.UTF_8);

        // Inject runid at top-level (not inside results)
        try {
            ObjectMapper mapper = new ObjectMapper();
            JsonNode rootNode = mapper.readTree(originalJson);

            if (rootNode.isObject()) {
                ((ObjectNode) rootNode).put("runid", runId);
            }

            return mapper.writerWithDefaultPrettyPrinter().writeValueAsString(rootNode);
        } catch (Exception e) {
            throw new RuntimeException("Failed to parse or inject runid into JSON", e);
        }
    }



    public static String getLatestFileKey(S3Client s3Client, String bucketName, String languagePrefix) {

        // Pattern to match filenames like "<languagePrefix>-YYYY-MM-DDTHH-MM.json"
        // Example: "kotlin-2025-07-29T14-30.json"
        // Captures the timestamp portion (YYYY-MM-DDTHH-MM) using a regex group
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
