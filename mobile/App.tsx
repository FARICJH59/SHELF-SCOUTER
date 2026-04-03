/**
 * App root – sets up the React Navigation stack and renders the app.
 */

import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createStackNavigator } from "@react-navigation/stack";
import { StatusBar } from "expo-status-bar";

import { CameraScreen } from "./src/screens/CameraScreen";
import { ResultsScreen } from "./src/screens/ResultsScreen";
import type { RootStackParamList } from "./src/types";

const Stack = createStackNavigator<RootStackParamList>();

export default function App() {
  return (
    <NavigationContainer>
      <StatusBar style="light" />
      <Stack.Navigator
        initialRouteName="Camera"
        screenOptions={{
          headerStyle: { backgroundColor: "#0f172a" },
          headerTintColor: "#f8fafc",
          headerTitleStyle: { fontWeight: "700" },
          cardStyle: { backgroundColor: "#0f172a" },
        }}
      >
        <Stack.Screen
          name="Camera"
          component={CameraScreen}
          options={{ title: "Shelf Scouter", headerShown: false }}
        />
        <Stack.Screen
          name="Results"
          component={ResultsScreen}
          options={{ title: "Scan Results" }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
