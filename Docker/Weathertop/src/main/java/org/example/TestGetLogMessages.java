package org.example;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.weathertop.service.GetLogMessages;
import com.weathertop.service.SDKStats;

public class TestGetLogMessages {

    public static void main(String[] args) throws JsonProcessingException {
        GetLogMessages logs = new GetLogMessages();

        String lang = "python" ;
        String JSON = logs.getHistoricalSummary(lang);
        System.out.println(JSON);
    }
}
