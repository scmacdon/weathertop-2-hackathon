// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package org.example;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.weathertop.service.QueryLatestFromS3;

public class TestQueryLatestFromS3 {

    public static void main(String[] args) throws JsonProcessingException {
        QueryLatestFromS3 wt = new QueryLatestFromS3();
        String json = wt.readJsonFromS3("python");
        System.out.println(json);
    }
}
