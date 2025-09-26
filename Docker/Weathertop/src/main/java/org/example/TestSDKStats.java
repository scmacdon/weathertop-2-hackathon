// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package org.example;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.weathertop.service.SDKStats;

public class TestSDKStats {

    public static void main(String[] args) throws JsonProcessingException {
        SDKStats langStats = new SDKStats();

     //   String[] langs = {"java", "kotlin", "dotnetv4", "php", "javascriptv3", "python", "gov2"};
     //   String JSON = langStats.getCoverageSummary(langs);
     //   System.out.println(JSON);


        String[] langs = {"dotnetv4", "ruby"};
        String JSON = langStats.getNoTestsBySDK(langs);

        System.out.println("NO Tests JSON");
        System.out.println(JSON);

    }
}
