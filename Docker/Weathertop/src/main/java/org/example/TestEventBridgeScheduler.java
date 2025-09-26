package org.example;

import com.weathertop.service.EventBridgeScheduler;
import com.weathertop.service.FargateTaskRunner;

public class TestEventBridgeScheduler {

    public static void main(String[] args) {

        /*
        // .NET
        String taskDefinitionArnVal = "arn:aws:ecs:us-east-1:814548047983:task-definition/WeathertopNet:2";
        String clusterName = "MyNetWeathertopCluster";
        String cron = "cron(0 0 ? * SUN *)";
        String ruleName = "ecs-dotnet-schedule";
        */

        // JAVAScript
       // String taskDefinitionArnVal = "arn:aws:ecs:us-east-1:814548047983:task-definition/WeathertopJS:3";
       // String clusterName = "MyJSWeathertopCluster";
       // String cron = "cron(59 23 ? * FRI *)";
       // String ruleName = "ecs-js-schedule";

        // PHP
        String taskDefinitionArnVal = "arn:aws:ecs:us-east-1:814548047983:task-definition/WeathertopPhp:4";
        String clusterName = "MyPHPWeathertopCluster";
        String cron = "cron(59 23 ? * FRI *)";
        String ruleName = "ecs-php-schedule";



        EventBridgeScheduler schedule = new EventBridgeScheduler();
        String message = schedule.setScheduler(taskDefinitionArnVal, clusterName, cron,ruleName );
        System.out.println(message);

    }
}