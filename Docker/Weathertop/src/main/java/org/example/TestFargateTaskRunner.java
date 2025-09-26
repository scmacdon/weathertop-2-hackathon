package org.example;

import com.weathertop.service.FargateTaskRunner;
import com.weathertop.service.HistoricalSDK;

public class TestFargateTaskRunner {
public static void main(String[] args) {
    FargateTaskRunner runner = new FargateTaskRunner();
   // String taskRunId = runner.runFargateTask("WeathertopJava");


    // .NET Container
   // String clusterName = "MyNetWeathertopCluster";
  //  String defName = "WeathertopNet";

    // JavaScript Container
    //String clusterName = "MyJSWeathertopCluster";
    //String defName = "WeathertopJS";

    // PHP Container

    String clusterName = "MyGoWeathertopCluster";
    String defName = "WeathertopGo";  // Your PHP task definition family name


    String taskRunId = runner.runFargateTask(defName, clusterName);
    System.out.println("Task run id is "+taskRunId);
    }
}
