// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package org.example;

import com.weathertop.service.HistoricalSDK;

public class TestHistoricalSDK{

    public static void main(String[] args) {
        HistoricalSDK history = new HistoricalSDK();
        String json = history.getHistoricalSummary("java");
        System.out.println(json);
    }
}
